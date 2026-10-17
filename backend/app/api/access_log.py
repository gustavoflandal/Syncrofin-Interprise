"""Reading the access log, and setting how long it is kept.

The administrator sees every access to the instance; each person sees their own. Both read
`audit_events` through the fixed set of access actions (`core/access_log.py`) and skip rows already
anonymised: those no longer say who or from where. Reading never writes to the trail.
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# The audit module's own query helpers: the access log is the same rows, filtered, in the same formats.
from app.api.audit import EXPORT_LIMIT, AuditPage, _csv, _filters, _page, _select_with_actor
from app.core.access_log import ACCESS_ACTIONS, ACCESS_MAX_RETENTION_DAYS, ACCESS_MIN_RETENTION_DAYS
from app.core.audit import seal
from app.core.auth import current_active_user, current_superuser
from app.core.database import get_async_session
from app.models.audit import AuditEvent
from app.models.user import User
from app.services import access_log_service

router = APIRouter(tags=["access-log"])


class RetentionRead(BaseModel):
    days: int
    minimum: int = ACCESS_MIN_RETENTION_DAYS
    maximum: int = ACCESS_MAX_RETENTION_DAYS


class RetentionWrite(BaseModel):
    days: int = Field(ge=ACCESS_MIN_RETENTION_DAYS, le=ACCESS_MAX_RETENTION_DAYS)


class AccessHistoryItem(BaseModel):
    """What a person is shown about their own access: no hash, no one else's details."""

    id: uuid.UUID
    occurred_at: datetime
    action: str
    actor_kind: str
    detail: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None


class AccessHistoryPage(BaseModel):
    items: list[AccessHistoryItem]
    total: int
    page: int
    limit: int


def _conditions(
    *,
    date_from: datetime | None,
    date_to: datetime | None,
    actor_user_id: uuid.UUID | None,
    ip: str | None,
    action: str | None,
) -> list:
    if action is not None and action not in ACCESS_ACTIONS:
        raise HTTPException(status_code=422, detail="UNKNOWN_ACCESS_ACTION")
    conditions = _filters(
        workspace_id=None, date_from=date_from, date_to=date_to, actor_user_id=actor_user_id,
        entity_type=None, entity_id=None, action=action,
    )
    conditions.append(AuditEvent.action.in_(ACCESS_ACTIONS))
    conditions.append(AuditEvent.purged_at.is_(None))
    if ip:
        conditions.append(AuditEvent.ip == ip)
    return conditions


# --- the whole instance (administrator) --------------------------------------------------


@router.get("/api/admin/access-log", response_model=AuditPage)
async def list_access_log(
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
    actor_user_id: Optional[uuid.UUID] = None,
    ip: Optional[str] = None,
    action: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    conditions = _conditions(date_from=date_from, date_to=date_to, actor_user_id=actor_user_id, ip=ip, action=action)
    return await _page(session, conditions, page, limit)


@router.get("/api/admin/access-log/export")
async def export_access_log(
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
    actor_user_id: Optional[uuid.UUID] = None,
    ip: Optional[str] = None,
    action: Optional[str] = None,
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    conditions = _conditions(date_from=date_from, date_to=date_to, actor_user_id=actor_user_id, ip=ip, action=action)
    await seal(session)  # so the file carries the hashes
    rows = (
        await session.execute(
            _select_with_actor().where(*conditions).order_by(AuditEvent.occurred_at.asc(), AuditEvent.id.asc()).limit(EXPORT_LIMIT)
        )
    ).all()
    return StreamingResponse(
        iter([_csv([(event, email) for event, email in rows])]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="registros-de-acesso.csv"'},
    )


@router.get("/api/admin/access-log/retention", response_model=RetentionRead)
async def get_retention(
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    return RetentionRead(days=await access_log_service.retention_days(session))


@router.put("/api/admin/access-log/retention", response_model=RetentionRead)
async def put_retention(
    body: RetentionWrite,
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    return RetentionRead(days=await access_log_service.set_retention_days(session, body.days))


# --- a person's own accesses ---------------------------------------------------------------


@router.get("/api/auth/access-history", response_model=AccessHistoryPage)
async def my_access_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """The signed-in person's own accesses. The person comes from the session, never from the request."""
    conditions = [
        AuditEvent.action.in_(ACCESS_ACTIONS),
        AuditEvent.purged_at.is_(None),
        AuditEvent.actor_user_id == user.id,
    ]
    total = (await session.execute(select(func.count()).select_from(AuditEvent).where(*conditions))).scalar_one()
    rows = (
        await session.execute(
            select(AuditEvent)
            .where(*conditions)
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).scalars().all()
    items = [AccessHistoryItem.model_validate(row, from_attributes=True) for row in rows]
    return AccessHistoryPage(items=items, total=total, page=page, limit=limit)
