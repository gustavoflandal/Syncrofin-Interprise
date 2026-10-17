"""Keeping the access log: what the trail cannot see for itself, how long it is kept, and the daily anonymising.

Logins, failures, locks and ended sessions are recorded where they happen (`session_service`, `login_guard`).
An API token has no sign-in, so its use is recorded here, when it authenticates.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_log import ACCESS_MAX_RETENTION_DAYS, ACCESS_MIN_RETENTION_DAYS
from app.core.audit import record_event
from app.core.audit_context import current_context, set_actor
from app.core.config import get_settings
from app.core.redis import get_redis
from app.models.api_token import ApiToken
from app.models.app_settings import AppSetting

logger = logging.getLogger(__name__)

#: A token used from one address is one access per hour, not one per request.
TOKEN_ACCESS_WINDOW_SECONDS = 3600

RETENTION_KEY = "access_log_retention_days"
#: Rows anonymised per statement, so one run never holds a long lock.
PURGE_BATCH = 10_000


def _window_key(token_id, ip: str | None) -> str:
    return f"token_access:{token_id}:{ip or '-'}"


async def _first_use_in_window(token_id, ip: str | None) -> bool:
    """True for the first use of this token from this address in the last hour.

    If Redis cannot be asked, the answer is yes: an access is recorded twice rather than not at all,
    and a request never fails because of the log.
    """
    try:
        redis = await get_redis()
        return bool(await redis.set(_window_key(token_id, ip), "1", nx=True, ex=TOKEN_ACCESS_WINDOW_SECONDS))
    except Exception:
        logger.warning("Could not check the token-access window; recording the access anyway", exc_info=True)
        return True


async def _forget_window(token_id, ip: str | None) -> None:
    """Best effort: let the next use record the access again after a write that failed. Never raises."""
    try:
        redis = await get_redis()
        await redis.delete(_window_key(token_id, ip))
    except Exception:
        logger.debug("Could not clear the token-access window", exc_info=True)


async def record_token_access(session: AsyncSession, row: ApiToken) -> None:
    """Record that `row` authenticated, at most once per hour for each address it comes from.

    The log never makes a request fail: the insert runs in a savepoint, so if it fails only the insert is undone
    (the caller's objects stay usable) and the request goes on. The same goes for the commit. If the commit
    itself fails the session is rolled back, which expires the caller's objects: the caller refreshes them.
    """
    ctx = current_context()
    if not await _first_use_in_window(row.id, ctx.ip):
        return
    committing = False
    try:
        async with session.begin_nested():
            set_actor(row.user_id, "api_token")
            await record_event(
                session,
                "token_access",
                "api_token",
                entity_id=row.id,
                workspace_id=row.workspace_id,
                detail=f"api_token:{row.prefix}",
            )
        committing = True
        await session.commit()
    except Exception:
        # `row.id` is read before the rollback: a rollback expires the instance.
        token_id = row.id
        logger.warning("Could not record the access of API token %s; the request goes on", token_id, exc_info=True)
        if committing:
            try:
                await session.rollback()
            except Exception:
                logger.debug("Could not roll back after a failed commit of the access log", exc_info=True)
        await _forget_window(token_id, ctx.ip)


async def retention_days(db: AsyncSession) -> int:
    """How long access records are kept: the saved value, else the environment's, held to 183..3650.

    A value saved by some other route (the generic settings endpoint) is clamped here, and the database
    refuses to anonymise anything under 183 days whatever this returns.
    """
    row = await db.get(AppSetting, RETENTION_KEY)
    for candidate in (row.value if row is not None else None, get_settings().access_log_retention_days):
        try:
            days = int(candidate)  # ty: ignore[invalid-argument-type]
        except (TypeError, ValueError):
            continue
        return max(ACCESS_MIN_RETENTION_DAYS, min(days, ACCESS_MAX_RETENTION_DAYS))
    return ACCESS_MIN_RETENTION_DAYS


async def set_retention_days(db: AsyncSession, days: int) -> int:
    """Save the retention period. The change is audited like every other setting."""
    if not ACCESS_MIN_RETENTION_DAYS <= days <= ACCESS_MAX_RETENTION_DAYS:
        raise ValueError(f"The retention period is between {ACCESS_MIN_RETENTION_DAYS} and {ACCESS_MAX_RETENTION_DAYS} days")
    row = await db.get(AppSetting, RETENTION_KEY)
    if row is None:
        db.add(AppSetting(key=RETENTION_KEY, value=str(days)))
    else:
        row.value = str(days)
    await db.commit()
    return days


async def purge_expired(db: AsyncSession, batch: int = PURGE_BATCH) -> int:
    """Anonymise every access event older than the retention period. Returns how many.

    Runs in batches, each in its own transaction. Something was done, so the trail says so (a system event),
    also when a later batch fails (the error then goes on to the caller).
    """
    batch = max(1, batch)
    days = await retention_days(db)
    total = 0
    try:
        while True:
            done = (
                await db.execute(text("SELECT audit_events_purge_access(:days, :batch)"), {"days": days, "batch": batch})
            ).scalar_one()
            await db.commit()
            total += done
            # With FOR UPDATE SKIP LOCKED a run that meets a concurrent run can get fewer than `batch` rows while
            # more are still due, so it may stop early: the next daily run catches up.
            if done < batch:
                break
    finally:
        # Batches already committed did anonymise data, even if a later one failed: the trail says so either way.
        if total:
            try:
                # A database-level failure leaves the transaction aborted (nothing else would be accepted), and the
                # earlier batches are already committed, each in its own transaction: start from a clean one.
                await db.rollback()
                await record_event(db, "access_log_purged", "audit_events", detail=f"{total} events, {days} days")
                await db.commit()
            except Exception:
                logger.warning("Could not record that %s access events were anonymised", total, exc_info=True)
    return total
