"""Staying signed in and signing out: refresh, logout, and the list of a person's devices."""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import current_active_user
from app.core.audit_context import set_actor
from app.core.database import get_async_session
from app.models.user import User
from app.models.user_session import UserSession
from app.services import session_service

router = APIRouter()


class RefreshBody(BaseModel):
    """Only for clients that cannot hold the cookie (the phone app)."""

    refresh_token: Optional[str] = None


class SessionRead(BaseModel):
    id: uuid.UUID
    device_label: Optional[str] = None
    ip: Optional[str] = None
    auth_method: str
    created_at: datetime
    last_seen_at: datetime
    current: bool


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    body: Optional[RefreshBody] = Body(default=None),
    db: AsyncSession = Depends(get_async_session),
):
    """A new access token, and a rotated refresh token, for a valid refresh token."""
    presented = request.cookies.get(session_service.REFRESH_COOKIE) or (body.refresh_token if body else None)
    if not presented:
        raise HTTPException(status_code=401, detail="No session")
    try:
        return await session_service.refresh(db, presented, request, response)
    except session_service.RefreshRejected:
        session_service.clear_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Session ended", headers=_clear_cookie_header())


def _clear_cookie_header() -> dict[str, str]:
    # HTTPException discards the `response` object's headers, so the cookie is cleared here too.
    return {
        "Set-Cookie": (
            f"{session_service.REFRESH_COOKIE}=; Max-Age=0; Path={session_service.REFRESH_COOKIE_PATH}; "
            "HttpOnly; SameSite=strict"
        )
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    body: Optional[RefreshBody] = Body(default=None),
    db: AsyncSession = Depends(get_async_session),
):
    """End the session this request belongs to (by access token or by refresh token). Always 200."""
    row: UserSession | None = None
    sid = session_service.session_id_from_request(request)
    if sid is not None:
        row = await db.get(UserSession, sid)
    if row is None:
        presented = request.cookies.get(session_service.REFRESH_COOKIE) or (body.refresh_token if body else None)
        if presented:
            row = await session_service.find_by_refresh_token(db, presented)
    if row is not None and row.revoked_at is None:
        await session_service.revoke(db, row, "logout", actor=row.user_id)
        await db.commit()
    session_service.clear_refresh_cookie(response)
    return {"detail": "Logged out"}


@router.get("/sessions", response_model=list[SessionRead])
async def list_sessions(
    request: Request,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    current = session_service.session_id_from_request(request)
    rows = await session_service.list_active(db, user.id)
    return [
        SessionRead(
            id=row.id,
            device_label=row.device_label,
            ip=row.ip,
            auth_method=row.auth_method,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            current=row.id == current,
        )
        for row in rows
    ]


@router.post("/sessions/revoke-others")
async def revoke_other_sessions(
    request: Request,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    keep = session_service.session_id_from_request(request)
    count = await session_service.revoke_all(db, user.id, "revoked_by_user", except_id=keep)
    await db.commit()
    return {"revoked": count}


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    response: Response,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_async_session),
):
    row = await db.get(UserSession, session_id)
    # Someone else's session is "not found", not "forbidden": it tells nothing about it.
    if row is None or row.user_id != user.id or row.revoked_at is not None:
        raise HTTPException(status_code=404, detail="Session not found")
    set_actor(user.id)
    await session_service.revoke(db, row, "revoked_by_user")
    await db.commit()
    if row.id == session_service.session_id_from_request(request):
        session_service.clear_refresh_cookie(response)
