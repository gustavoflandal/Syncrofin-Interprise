"""API tokens of the current workspace: make one, list them, rotate, revoke.

Needs `tokens.manage` (an owner has it). The token's secret is returned **once**, by the call that makes it
(or rotates it), and cannot be read again. A token cannot use these routes: a credential that lives in a script
must not be able to mint another.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_context import current_context
from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, require_permission
from app.models.api_token import ApiToken
from app.services import api_token_service

router = APIRouter(prefix="/api/api-tokens", tags=["api-tokens"])

_manage = require_permission("tokens.manage")


async def _by_a_person(ctx: WorkspaceContext = Depends(_manage)) -> WorkspaceContext:
    if current_context().api_token_id is not None:
        raise HTTPException(status_code=403, detail="An API token cannot manage API tokens")
    return ctx


class TokenRead(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime
    last_used_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    #: active | expired | revoked
    state: str
    #: Who it acts as.
    user_email: Optional[str] = None


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str]
    days: int = Field(default=90, ge=1, le=api_token_service.MAX_DAYS)


class TokenCreated(BaseModel):
    #: The secret. Shown here and never again.
    token: str
    item: TokenRead


def _state(row: ApiToken) -> str:
    if row.revoked_at is not None:
        return "revoked"
    return "active" if row.expires_at > datetime.now(timezone.utc) else "expired"


def _read(row: ApiToken, email: str | None) -> TokenRead:
    return TokenRead(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        scopes=list(row.scopes or []),
        created_at=row.created_at,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        state=_state(row),
        user_email=email,
    )


@router.get("", response_model=list[TokenRead])
async def list_tokens(
    ctx: WorkspaceContext = Depends(_by_a_person),
    session: AsyncSession = Depends(get_async_session),
):
    return [_read(row, email) for row, email in await api_token_service.list_tokens(session, ctx.id)]


@router.post("", response_model=TokenCreated, status_code=status.HTTP_201_CREATED)
async def create_token(
    body: TokenCreate,
    ctx: WorkspaceContext = Depends(_by_a_person),
    session: AsyncSession = Depends(get_async_session),
):
    row, secret = await api_token_service.create_token(
        session,
        workspace_id=ctx.id,
        user=ctx.user,
        creator_permissions=ctx.permissions or frozenset(),
        name=body.name,
        scopes=body.scopes,
        days=body.days,
    )
    await session.commit()
    return TokenCreated(token=secret, item=_read(row, ctx.user.email))


@router.post("/{token_id}/rotate", response_model=TokenCreated, status_code=status.HTTP_201_CREATED)
async def rotate_token(
    token_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_by_a_person),
    session: AsyncSession = Depends(get_async_session),
):
    """A new token with the same name, scopes and lifetime; the old one stops working at once."""
    old = await api_token_service.get_token(session, ctx.id, token_id)
    if not api_token_service.is_usable(old):
        raise HTTPException(status_code=409, detail="Only an active token can be rotated")
    days = max(1, min(api_token_service.MAX_DAYS, round((old.expires_at - old.created_at).total_seconds() / 86400)))
    # The new token belongs to whoever rotates it, and cannot carry more than they can do.
    row, secret = await api_token_service.create_token(
        session,
        workspace_id=ctx.id,
        user=ctx.user,
        creator_permissions=ctx.permissions or frozenset(),
        name=old.name,
        scopes=list(old.scopes or []),
        days=days,
    )
    await api_token_service.revoke(session, old)
    await session.commit()
    return TokenCreated(token=secret, item=_read(row, ctx.user.email))


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_by_a_person),
    session: AsyncSession = Depends(get_async_session),
):
    row = await api_token_service.get_token(session, ctx.id, token_id)
    await api_token_service.revoke(session, row)
    await session.commit()
