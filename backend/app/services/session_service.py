"""Signing in, staying signed in, and being signed out.

Every route that used to mint a 24-hour JWT calls `sign_in` instead: it opens a
`UserSession`, returns a short-lived access token that names it, and hands the browser a
refresh token in an `httpOnly` cookie (JavaScript never sees it). Clients that cannot hold
cookies (the phone app) ask for the refresh token in the response body with the header
`X-Refresh-Mode: body`.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Request, Response
from fastapi_users.jwt import decode_jwt, generate_jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_event
from app.core.audit_context import current_context, set_actor
from app.core.config import get_settings
from app.models.user import User
from app.models.user_session import UserSession
from app.services import login_guard
from app.services.mfa_policy import VERIFIED_METHODS

logger = logging.getLogger(__name__)

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/api/auth"
#: Header a client sends to get the refresh token in the JSON body instead of a cookie.
BODY_MODE_HEADER = "x-refresh-mode"

#: Two tabs refreshing together both present the same token; the second one is not theft.
REUSE_GRACE = timedelta(seconds=10)
#: How often a request is allowed to write `last_seen_at`.
TOUCH_EVERY = timedelta(seconds=60)

_AUDIENCE = ["fastapi-users:auth"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


MOBILE_CLIENT = "syncrofin-mobile"


def device_label(user_agent: str | None, client: str | None = None) -> str:
    """A rough "Browser on System" from the User-Agent, for a person's own device list.

    `client` is the `X-Client` header the phone app sends: the User-Agent of a web view says
    "Chrome on Android", which is true and useless to someone with a browser on the same phone.
    """
    ua = user_agent or ""
    if not ua and client != MOBILE_CLIENT:
        return "Dispositivo desconhecido"
    if client == MOBILE_CLIENT or "SyncroFin-Mobile" in ua:
        browser = "App SyncroFin"
    elif re.search(r"Edg/", ua):
        browser = "Edge"
    elif re.search(r"OPR/|Opera", ua):
        browser = "Opera"
    elif re.search(r"Firefox/", ua):
        browser = "Firefox"
    elif re.search(r"Chrome/", ua):
        browser = "Chrome"
    elif re.search(r"Safari/", ua):
        browser = "Safari"
    else:
        browser = ua.split("/")[0][:40] or "Cliente"
    if re.search(r"Android", ua):
        system = "Android"
    elif re.search(r"iPhone|iPad|iOS", ua):
        system = "iOS"
    elif re.search(r"Windows", ua):
        system = "Windows"
    elif re.search(r"Mac OS X|Macintosh", ua):
        system = "macOS"
    elif re.search(r"Linux|X11", ua):
        system = "Linux"
    else:
        return browser
    return f"{browser} em {system}"


# --- access tokens -------------------------------------------------------------------------


def access_lifetime_seconds() -> int:
    return get_settings().access_token_expire_minutes * 60


def write_access_token(user: User, session_id: uuid.UUID) -> str:
    settings = get_settings()
    return generate_jwt(
        {"sub": str(user.id), "aud": _AUDIENCE, "sid": str(session_id)},
        settings.secret_key.get_secret_value(),
        access_lifetime_seconds(),
        algorithm=settings.algorithm,
    )


def read_access_claims(token: str | None) -> dict | None:
    """The claims of a valid, unexpired access token; None for anything else."""
    if not token:
        return None
    settings = get_settings()
    try:
        return decode_jwt(
            token, settings.secret_key.get_secret_value(), _AUDIENCE, algorithms=[settings.algorithm]
        )
    except Exception:  # bad signature, expired, malformed: all the same to the caller
        return None


def session_id_from_request(request: Request) -> uuid.UUID | None:
    """The session an `Authorization: Bearer` header belongs to, if it has a good one."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    claims = read_access_claims(token)
    try:
        return uuid.UUID(claims["sid"]) if claims and claims.get("sid") else None
    except ValueError:
        return None


# --- lifecycle -------------------------------------------------------------------------------


def is_active(row: UserSession, now: datetime | None = None) -> bool:
    now = now or _now()
    settings = get_settings()
    if row.revoked_at is not None or row.expires_at <= now:
        return False
    return now - row.last_refreshed_at <= timedelta(days=settings.session_idle_days)


async def _open(
    db: AsyncSession, user: User, request: Request, method: str
) -> tuple[UserSession, str]:
    settings = get_settings()
    refresh = _new_refresh_token()
    ctx = current_context()
    user_agent = (ctx.user_agent or request.headers.get("user-agent") or "")[:300] or None
    row = UserSession(
        user_id=user.id,
        refresh_hash=hash_refresh_token(refresh),
        expires_at=_now() + timedelta(days=settings.session_max_days),
        ip=ctx.ip,
        user_agent=user_agent,
        device_label=device_label(user_agent, request.headers.get("x-client")),
        auth_method=method,
        mfa_verified=method in VERIFIED_METHODS,
    )
    db.add(row)
    await db.flush()
    return row, refresh


async def _is_new_device(db: AsyncSession, user: User, request: Request) -> bool:
    """True when this person has signed in before, but never from this browser and system.

    The first sign-in ever is not news (they just made the account), so it is not one. A "device" is
    what `device_label` says: it is not a fingerprint, only enough for "was this you?" to be a fair question.
    """
    ctx = current_context()
    user_agent = (ctx.user_agent or request.headers.get("user-agent") or "")[:300] or None
    label = device_label(user_agent, request.headers.get("x-client"))
    seen = (
        await db.execute(
            select(UserSession.device_label).where(UserSession.user_id == user.id).distinct()
        )
    ).scalars().all()
    return bool(seen) and label not in seen


def _tell_new_device(user: User, row: UserSession) -> None:
    from app.services import email_service, email_templates

    try:
        subject, body = email_templates.new_device_login(
            (user.preferences or {}).get("language"),
            device=row.device_label or "?",
            ip=row.ip,
            when=_now().strftime("%Y-%m-%d %H:%M"),
            link=email_service.frontend_link("/settings"),
        )
        email_service.send_in_background(user.email, subject, body)
    except Exception:  # a notice must never stop a sign-in
        logger.warning("Could not send the new-device notice for user %s", user.id, exc_info=True)


def wants_body_mode(request: Request) -> bool:
    return request.headers.get(BODY_MODE_HEADER, "").lower() == "body"


def set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.session_max_days * 24 * 3600,
        httponly=True,
        secure=settings.frontend_url.lower().startswith("https"),
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH)


def _tokens(user: User, row: UserSession, refresh: str | None, body_mode: bool) -> dict:
    result: dict = {
        "access_token": write_access_token(user, row.id),
        "token_type": "bearer",
        "expires_in": access_lifetime_seconds(),
    }
    if body_mode and refresh:
        result["refresh_token"] = refresh
    return result


async def sign_in(
    db: AsyncSession, user: User, request: Request, response: Response, method: str = "password"
) -> dict:
    """Open a session for a user who has proved who they are, and return the tokens."""
    new_device = await _is_new_device(db, user, request)
    row, refresh = await _open(db, user, request, method)
    set_actor(user.id)
    await record_event(db, "login", "user_session", entity_id=row.id, detail=method)
    await db.commit()
    await login_guard.succeeded(db, user)
    if new_device:
        _tell_new_device(user, row)
    body_mode = wants_body_mode(request)
    if not body_mode:
        set_refresh_cookie(response, refresh)
    return _tokens(user, row, refresh, body_mode)


async def sign_in_redirect(
    db: AsyncSession, user: User, request: Request, response: Response, method: str
) -> None:
    """Open a session and put the refresh token in the cookie of `response`, with no body.

    For the OIDC callback, which answers with a redirect: the page it lands on trades the
    cookie for an access token, so no token travels in a URL.
    """
    new_device = await _is_new_device(db, user, request)
    row, refresh = await _open(db, user, request, method)
    set_actor(user.id)
    await record_event(db, "login", "user_session", entity_id=row.id, detail=method)
    await db.commit()
    if new_device:
        _tell_new_device(user, row)
    set_refresh_cookie(response, refresh)


class RefreshRejected(Exception):
    """The refresh token is unknown, expired, revoked, or was replayed."""


async def refresh(
    db: AsyncSession, presented: str, request: Request, response: Response
) -> dict:
    """Trade a refresh token for a new access token, rotating the refresh token."""
    hashed = hash_refresh_token(presented)
    now = _now()
    row = (
        await db.execute(select(UserSession).where(UserSession.refresh_hash == hashed).with_for_update())
    ).scalar_one_or_none()

    if row is None:
        replayed = (
            await db.execute(
                select(UserSession).where(UserSession.previous_refresh_hash == hashed).with_for_update()
            )
        ).scalar_one_or_none()
        if replayed is None:
            raise RefreshRejected("unknown")
        if replayed.revoked_at is None and replayed.rotated_at and now - replayed.rotated_at <= REUSE_GRACE:
            # A second tab (or a retry) that presented the token a moment after it rotated. The
            # first response already gave the client the new one, so only an access token is due.
            user = await db.get(User, replayed.user_id)
            if user is None or not user.is_active:
                raise RefreshRejected("inactive")
            return _tokens(user, replayed, None, wants_body_mode(request))
        if replayed.revoked_at is None:
            # An old token, presented after the grace: someone kept a copy. Kill the session.
            await revoke(db, replayed, "refresh_reuse", actor=replayed.user_id)
            await db.commit()
        raise RefreshRejected("reuse")

    if not is_active(row, now):
        raise RefreshRejected("expired")
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise RefreshRejected("inactive")

    new = _new_refresh_token()
    row.previous_refresh_hash = row.refresh_hash
    row.refresh_hash = hash_refresh_token(new)
    row.rotated_at = now
    row.last_refreshed_at = now
    row.last_seen_at = now
    await db.commit()

    body_mode = wants_body_mode(request)
    if not body_mode:
        set_refresh_cookie(response, new)
    return _tokens(user, row, new, body_mode)


async def revoke(
    db: AsyncSession, row: UserSession, reason: str, actor: uuid.UUID | None = None
) -> None:
    if row.revoked_at is not None:
        return
    row.revoked_at = _now()
    row.revoked_reason = reason
    if actor is not None:
        set_actor(actor)
    await record_event(db, "session_revoked", "user_session", entity_id=row.id, detail=reason)


async def revoke_all(
    db: AsyncSession, user_id: uuid.UUID, reason: str, except_id: uuid.UUID | None = None
) -> int:
    """End every session of a user (except one), e.g. after a password change."""
    rows = (
        await db.execute(
            select(UserSession).where(
                UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
            )
        )
    ).scalars().all()
    count = 0
    for row in rows:
        if row.id == except_id:
            continue
        await revoke(db, row, reason)
        count += 1
    return count


async def mark_mfa_verified(db: AsyncSession, session_id: uuid.UUID | None) -> None:
    """The person just proved they hold a second factor (typed the first code, registered a passkey)."""
    if session_id is None:
        return
    await db.execute(update(UserSession).where(UserSession.id == session_id).values(mfa_verified=True))
    await db.commit()


async def touch(db: AsyncSession, row: UserSession) -> None:
    """Record activity, at most once a minute so a busy screen does not write on every call."""
    now = _now()
    if now - row.last_seen_at < TOUCH_EVERY:
        return
    await db.execute(update(UserSession).where(UserSession.id == row.id).values(last_seen_at=now))
    await db.commit()


async def list_active(db: AsyncSession, user_id: uuid.UUID) -> list[UserSession]:
    rows = (
        await db.execute(
            select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .order_by(UserSession.last_seen_at.desc())
        )
    ).scalars().all()
    now = _now()
    return [row for row in rows if is_active(row, now)]


async def find_by_refresh_token(db: AsyncSession, presented: str) -> UserSession | None:
    return (
        await db.execute(
            select(UserSession).where(UserSession.refresh_hash == hash_refresh_token(presented))
        )
    ).scalar_one_or_none()
