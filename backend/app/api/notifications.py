import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, current_workspace
from app.services import notification_delivery, notification_service

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationRead(BaseModel):
    id: uuid.UUID
    kind: str
    severity: str
    title: str
    body: str
    data: Optional[dict[str, Any]] = None
    created_at: datetime
    read_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UnreadCount(BaseModel):
    unread: int


@router.get("", response_model=list[NotificationRead])
async def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await notification_service.list_for_user(
        session, ctx.workspace.id, ctx.user_id, unread_only=unread_only, limit=limit
    )


@router.get("/unread-count", response_model=UnreadCount)
async def unread_count(
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return UnreadCount(
        unread=await notification_service.unread_count(session, ctx.workspace.id, ctx.user_id)
    )


@router.post("/refresh", response_model=UnreadCount)
async def refresh(
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    """Run the generators now, for this workspace, instead of waiting for the
    hourly job. Idempotent, so pressing it repeatedly is harmless."""
    created = await notification_service.generate_for_workspace(session, ctx.workspace)
    await notification_delivery.deliver(session, created)
    await session.commit()
    return UnreadCount(
        unread=await notification_service.unread_count(session, ctx.workspace.id, ctx.user_id)
    )


@router.post("/read-all", response_model=UnreadCount)
async def read_all(
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    await notification_service.mark_all_read(session, ctx.workspace.id, ctx.user_id)
    await session.commit()
    return UnreadCount(unread=0)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_one(
    notification_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    changed = await notification_service.mark_read(
        session, ctx.workspace.id, ctx.user_id, notification_id
    )
    await session.commit()
    if not changed:
        # Either it is not yours, or it was already read; both are "nothing to do".
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
