"""Guessing a password should get nowhere, and should be noticed.

`authenticate` is the password check of `/auth/login` with three additions:

- **A lock.** After `LOGIN_MAX_ATTEMPTS` wrong passwords in a row the account stops accepting sign-ins for
  `LOGIN_LOCK_MINUTES`; each time it is locked again the pause doubles (up to an hour), and a good sign-in
  starts over. The IP limiter in front of the route slows one machine; this stops a slow guess spread across many.
- **One answer.** A wrong password, an unknown e-mail and a locked account all answer `LOGIN_BAD_CREDENTIALS`,
  so the response never says which accounts exist or which are locked. While locked, the password is still
  checked (and ignored), so the time taken does not give it away either. The person is told by e-mail.
- **A trail.** Every failure is an audit event (`login_failed`, `login_blocked`, `account_locked`,
  `account_unlocked`) with the reason: the access log an incident review asks for. The address typed is not kept (it is
  often a password typed in the wrong box, and the trail cannot be edited afterwards).

The counters are written with plain UPDATEs, never through the ORM, so they neither race with each other
(two wrong guesses at once both count) nor turn each attempt into a row-change audit event.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import cast

from fastapi_users.exceptions import UserNotExists
from sqlalchemy import CursorResult, case, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_event
from app.core.audit_context import set_actor
from app.core.config import get_settings
from app.models.user import User

logger = logging.getLogger(__name__)

#: However many times it has been locked, a pause never lasts longer than this. Anyone who knows an e-mail
#: address can lock that account, so a long pause would be a weapon: an hour is enough to make guessing
#: hopeless (five tries an hour) and short enough to wait out.
MAX_LOCK = timedelta(hours=1)
#: Wrong passwords older than this are forgotten: a slip last week is not part of a guessing run.
FORGET_AFTER = timedelta(hours=24)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def lock_duration(times_locked_before: int) -> timedelta:
    base = timedelta(minutes=max(1, get_settings().login_lock_minutes))
    # Capped exponent: `timedelta` overflows long before a person could be locked that many times.
    return min(base * (2 ** min(max(0, times_locked_before), 10)), MAX_LOCK)


def is_locked(user: User, now: datetime | None = None) -> bool:
    return user.locked_until is not None and user.locked_until > (now or _now())


async def _lookup(user_manager, email: str) -> User | None:
    try:
        return await user_manager.get_by_email(email)
    except UserNotExists:
        return None


async def authenticate(db: AsyncSession, user_manager, credentials) -> User | None:
    """The user for a good e-mail and password, or None for any reason at all (see the module docstring)."""
    email = (credentials.username or "").strip()
    credentials.username = email
    candidate = await _lookup(user_manager, email)

    if candidate is not None and is_locked(candidate):
        # Take as long as a real check would, and say nothing.
        user_manager.password_helper.verify_and_update(credentials.password, candidate.hashed_password)
        set_actor(candidate.id)
        await record_event(db, "login_blocked", "user", entity_id=candidate.id, detail="account_locked")
        await db.commit()
        return None

    user = await user_manager.authenticate(credentials)
    if user is None:
        await _register_failure(db, candidate)
        return None
    if not user.is_active:
        set_actor(user.id)
        await record_event(db, "login_failed", "user", entity_id=user.id, detail="inactive")
        await db.commit()
        return None
    # The lock may have been set by a guess that overlapped this one: the answer is taken from the row now.
    locked_until = (await db.execute(select(User.locked_until).where(User.id == user.id))).scalar_one_or_none()
    if locked_until is not None and locked_until > _now():
        set_actor(user.id)
        await record_event(db, "login_blocked", "user", entity_id=user.id, detail="account_locked")
        await db.commit()
        return None
    return user


async def succeeded(db: AsyncSession, user: User) -> None:
    """A good sign-in ends the run of failures and forgets earlier locks."""
    if not (user.failed_login_count or user.lock_count or user.locked_until):
        return
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(failed_login_count=0, lock_count=0, locked_until=None)
        .execution_options(synchronize_session=False)
    )
    await db.commit()


async def second_factor_failed(db: AsyncSession, user: User) -> None:
    """A wrong authenticator code after a right password counts toward the same lock."""
    await _register_failure(db, user, reason="bad_2fa_code")


async def password_failed(db: AsyncSession, user: User) -> None:
    """A wrong password typed where the person is already signed in (e.g. to turn off 2FA) counts too."""
    await _register_failure(db, user)


async def _register_failure(db: AsyncSession, user: User | None, reason: str = "bad_password") -> None:
    if user is None:
        # The address typed is not kept: it is often a password typed into the wrong box, and the trail
        # cannot be edited afterwards. The request's IP and user agent are on the event.
        await record_event(db, "login_failed", "user", detail="unknown_user")
        await db.commit()
        return

    settings = get_settings()
    now = _now()
    stale = User.last_failed_login_at < now - FORGET_AFTER
    row = (
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(
                failed_login_count=case((stale, 1), else_=User.failed_login_count + 1),
                last_failed_login_at=now,
            )
            .returning(User.failed_login_count, User.lock_count)
            .execution_options(synchronize_session=False)
        )
    ).one()
    attempts, times_locked = row.failed_login_count, row.lock_count
    set_actor(user.id)
    await record_event(db, "login_failed", "user", entity_id=user.id, detail=reason)

    locked = False
    if attempts >= max(1, settings.login_max_attempts):
        pause = lock_duration(times_locked)
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(locked_until=now + pause, lock_count=times_locked + 1, failed_login_count=0)
            .execution_options(synchronize_session=False)
        )
        await record_event(
            db,
            "account_locked",
            "user",
            entity_id=user.id,
            detail=f"{attempts} attempts, {int(pause.total_seconds() // 60)} min",
        )
        locked = True
    await db.commit()

    if locked:
        _tell_owner(user, attempts, int(pause.total_seconds() // 60))


def _tell_owner(user: User, attempts: int, minutes: int) -> None:
    from app.services import email_service, email_templates

    try:
        subject, body = email_templates.account_locked(
            (user.preferences or {}).get("language"),
            attempts=attempts,
            minutes=minutes,
            link=email_service.frontend_link("/forgot-password"),
        )
        email_service.send_in_background(user.email, subject, body)
    except Exception:  # the lock stands whether or not the mail can go out
        logger.warning("Could not send the lock notice for user %s", user.id, exc_info=True)


async def unlock(db: AsyncSession, user_id: uuid.UUID, *, reason: str) -> bool:
    """Lift a lock and clear the run of failures. False if there was nothing to clear."""
    result = await db.execute(
        update(User)
        .where(User.id == user_id)
        .where((User.locked_until.is_not(None)) | (User.failed_login_count > 0) | (User.lock_count > 0))
        .values(failed_login_count=0, lock_count=0, locked_until=None)
        .execution_options(synchronize_session=False)
    )
    if not cast(CursorResult, result).rowcount:
        return False
    await record_event(db, "account_unlocked", "user", entity_id=user_id, detail=reason)
    return True
