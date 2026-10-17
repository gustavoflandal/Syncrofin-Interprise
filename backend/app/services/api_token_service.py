"""Making, recognising and ending API tokens.

What a request with a token may do is decided in three places, all of which must agree:

1. the token's own **scopes** (chosen when it was made, never administrative);
2. what its **owner can do now** in the workspace (`WorkspaceContext` intersects the two, so
   demoting the owner shrinks their tokens at once, and removing them from the workspace ends them);
3. the routes: only the workspace's own routes accept a token. Anything that acts on the *person* (their
   account, sessions, passkeys, the administration of the instance) refuses one, and so does the
   management of tokens themselves: a token cannot mint another.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import inspect as sa_inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import permissions as catalog
from app.core.audit_context import current_context
from app.models.api_token import TOKEN_PREFIX, ApiToken
from app.models.user import User

MAX_DAYS = 365
MAX_TOKENS_PER_WORKSPACE = 100
TOUCH_EVERY = timedelta(minutes=1)

#: What a token can be given: any permission of the catalog except the administrative ones.
#: A credential that lives in a script has no business inviting people or making roles.
SCOPE_CHOICES: frozenset[str] = catalog.ALL_PERMISSIONS - catalog.ADMIN_PERMISSIONS


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def looks_like_api_token(value: str | None) -> bool:
    return bool(value) and value.startswith(TOKEN_PREFIX)  # type: ignore[union-attr]


def _new_secret() -> tuple[str, str]:
    """(the whole token, its visible prefix)."""
    prefix = TOKEN_PREFIX + secrets.token_hex(4)
    return f"{prefix}_{secrets.token_urlsafe(32)}", prefix


async def create_token(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user: User,
    creator_permissions: frozenset[str],
    name: str,
    scopes: list[str],
    days: int,
) -> tuple[ApiToken, str]:
    """A new token and its secret (the only time it is available)."""
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="A token needs a name")
    if not 1 <= days <= MAX_DAYS:
        raise HTTPException(status_code=400, detail=f"A token lasts between 1 and {MAX_DAYS} days")
    chosen = frozenset(scopes)
    if not chosen:
        raise HTTPException(status_code=400, detail="A token needs at least one scope")
    unknown = chosen - catalog.ALL_PERMISSIONS
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown scopes: {', '.join(sorted(unknown))}")
    administrative = chosen & catalog.ADMIN_PERMISSIONS
    if administrative:
        raise HTTPException(
            status_code=400, detail=f"A token cannot be given administrative scopes: {', '.join(sorted(administrative))}"
        )
    beyond = chosen - creator_permissions
    if beyond:
        raise HTTPException(
            status_code=403, detail=f"You cannot give a token what you cannot do yourself: {', '.join(sorted(beyond))}"
        )
    live = (
        await session.execute(
            select(ApiToken.id).where(ApiToken.workspace_id == workspace_id, ApiToken.revoked_at.is_(None))
        )
    ).scalars().all()
    if len(live) >= MAX_TOKENS_PER_WORKSPACE:
        raise HTTPException(status_code=400, detail=f"At most {MAX_TOKENS_PER_WORKSPACE} active tokens per workspace")
    secret, prefix = _new_secret()
    row = ApiToken(
        workspace_id=workspace_id,
        user_id=user.id,
        name=name,
        prefix=prefix,
        token_hash=hash_token(secret),
        scopes=sorted(chosen),
        expires_at=_now() + timedelta(days=days),
    )
    session.add(row)
    await session.flush()
    return row, secret


def is_usable(row: ApiToken, now: datetime | None = None) -> bool:
    return row.revoked_at is None and row.expires_at > (now or _now())


async def authenticate(session: AsyncSession, presented: str) -> tuple[ApiToken, User] | None:
    """The token and the person it acts as, or None for anything that is not a live token of an active user."""
    row = (await session.execute(select(ApiToken).where(ApiToken.token_hash == hash_token(presented)))).scalar_one_or_none()
    if row is None or not is_usable(row):
        return None
    user = await session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    await touch(session, row)
    # Imported here: `access_log_service` reads the audit context and Redis, which this module must not load at import.
    from app.services import access_log_service

    await access_log_service.record_token_access(session, row)
    # A failed write of the log rolls the session back, which expires what this request already loaded.
    for loaded in (row, user):
        if sa_inspect(loaded).expired:
            await session.refresh(loaded)
    # From here on the request knows it is a token and what it may do: the workspace context reads this.
    ctx = current_context()
    ctx.api_token_id = row.id
    ctx.api_token_prefix = row.prefix
    ctx.api_token_scopes = frozenset(row.scopes or []) & catalog.ALL_PERMISSIONS
    ctx.api_token_workspace_id = row.workspace_id
    return row, user


async def touch(session: AsyncSession, row: ApiToken) -> None:
    now = _now()
    if row.last_used_at is not None and now - row.last_used_at < TOUCH_EVERY:
        return
    await session.execute(update(ApiToken).where(ApiToken.id == row.id).values(last_used_at=now))
    await session.commit()


async def list_tokens(session: AsyncSession, workspace_id: uuid.UUID) -> list[tuple[ApiToken, str | None]]:
    rows = (
        await session.execute(
            select(ApiToken, User.email)
            .outerjoin(User, User.id == ApiToken.user_id)
            .where(ApiToken.workspace_id == workspace_id)
            .order_by(ApiToken.created_at.desc())
        )
    ).all()
    return [(token, email) for token, email in rows]


async def get_token(session: AsyncSession, workspace_id: uuid.UUID, token_id: uuid.UUID) -> ApiToken:
    row = await session.get(ApiToken, token_id)
    if row is None or row.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Token not found")
    return row


async def revoke(session: AsyncSession, row: ApiToken) -> None:
    if row.revoked_at is None:
        row.revoked_at = _now()
        await session.flush()
