"""Reading the audit trail. There is no route that writes to it: that is what the database enforces."""
import csv
import io
import json
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import seal
from app.core.auth import current_superuser
from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, current_workspace
from app.models.audit import VERIFY_QUERY, AuditEvent
from app.models.user import User

router = APIRouter(prefix="/api/audit", tags=["audit"])

EXPORT_LIMIT = 100_000


class AuditEventRead(BaseModel):
    id: uuid.UUID
    seq: Optional[int] = None
    occurred_at: datetime
    actor_user_id: Optional[uuid.UUID] = None
    actor_email: Optional[str] = None
    actor_kind: str
    workspace_id: Optional[uuid.UUID] = None
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    changes: Optional[dict[str, Any]] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    detail: Optional[str] = None
    hash: Optional[str] = None


class AuditPage(BaseModel):
    items: list[AuditEventRead]
    total: int
    page: int
    limit: int


class AuditFacets(BaseModel):
    entity_types: list[str]
    actions: list[str]


class AuditVerification(BaseModel):
    ok: bool
    checked: int
    head_seq: Optional[int] = None
    head_hash: Optional[str] = None
    broken_at_seq: Optional[int] = None
    reason: Optional[str] = None


def _filters(
    *,
    workspace_id: uuid.UUID | None,
    date_from: datetime | None,
    date_to: datetime | None,
    actor_user_id: uuid.UUID | None,
    entity_type: str | None,
    entity_id: str | None,
    action: str | None,
) -> list:
    conditions = []
    if workspace_id is not None:
        conditions.append(AuditEvent.workspace_id == workspace_id)
    if date_from is not None:
        conditions.append(AuditEvent.occurred_at >= date_from)
    if date_to is not None:
        conditions.append(AuditEvent.occurred_at <= date_to)
    if actor_user_id is not None:
        conditions.append(AuditEvent.actor_user_id == actor_user_id)
    if entity_type:
        conditions.append(AuditEvent.entity_type == entity_type)
    if entity_id:
        conditions.append(AuditEvent.entity_id == entity_id)
    if action:
        conditions.append(AuditEvent.action == action)
    return conditions


def _select_with_actor():
    return select(AuditEvent, User.email).outerjoin(User, User.id == AuditEvent.actor_user_id)


def _read(event: AuditEvent, email: str | None) -> AuditEventRead:
    data = AuditEventRead.model_validate(event, from_attributes=True)
    data.actor_email = email
    return data


async def _page(session: AsyncSession, conditions: list, page: int, limit: int) -> AuditPage:
    total = (
        await session.execute(select(func.count()).select_from(AuditEvent).where(*conditions))
    ).scalar_one()
    rows = (
        await session.execute(
            _select_with_actor()
            .where(*conditions)
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()
    return AuditPage(items=[_read(e, email) for e, email in rows], total=total, page=page, limit=limit)


def _csv(rows: list[tuple[AuditEvent, str | None]]) -> str:
    out = io.StringIO()
    out.write("﻿")  # Excel reads UTF-8 only with a BOM
    writer = csv.writer(out, delimiter=";")
    writer.writerow(
        ["seq", "quando_utc", "usuario", "tipo_ator", "acao", "entidade", "id", "alteracoes", "ip", "requisicao", "detalhe", "hash"]
    )
    for e, email in rows:
        writer.writerow(
            [
                e.seq or "",
                e.occurred_at.isoformat(),
                email or (str(e.actor_user_id) if e.actor_user_id else ""),
                e.actor_kind,
                e.action,
                e.entity_type,
                e.entity_id or "",
                json.dumps(e.changes, ensure_ascii=False) if e.changes else "",
                e.ip or "",
                e.request_id or "",
                e.detail or "",
                e.hash or "",
            ]
        )
    return out.getvalue()


# --- a workspace's own trail (owner) ---------------------------------------------------


@router.get("", response_model=AuditPage)
async def list_events(
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
    actor_user_id: Optional[uuid.UUID] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    ctx.require("audit.read")
    conditions = _filters(
        workspace_id=ctx.id, date_from=date_from, date_to=date_to, actor_user_id=actor_user_id,
        entity_type=entity_type, entity_id=entity_id, action=action,
    )
    return await _page(session, conditions, page, limit)


@router.get("/facets", response_model=AuditFacets)
async def facets(
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    ctx.require("audit.read")
    types = (
        await session.execute(
            select(AuditEvent.entity_type)
            .where(AuditEvent.workspace_id == ctx.id)
            .distinct()
            .order_by(AuditEvent.entity_type)
        )
    ).scalars().all()
    actions = (
        await session.execute(
            select(AuditEvent.action)
            .where(AuditEvent.workspace_id == ctx.id)
            .distinct()
            .order_by(AuditEvent.action)
        )
    ).scalars().all()
    return AuditFacets(entity_types=list(types), actions=list(actions))


@router.get("/export")
async def export_events(
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
    actor_user_id: Optional[uuid.UUID] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    ctx.require("audit.read")
    await seal(session)  # so the file carries the hashes
    conditions = _filters(
        workspace_id=ctx.id, date_from=date_from, date_to=date_to, actor_user_id=actor_user_id,
        entity_type=entity_type, entity_id=entity_id, action=action,
    )
    rows = (
        await session.execute(
            _select_with_actor()
            .where(*conditions)
            .order_by(AuditEvent.occurred_at.asc(), AuditEvent.id.asc())
            .limit(EXPORT_LIMIT)
        )
    ).all()
    return StreamingResponse(
        iter([_csv([(e, email) for e, email in rows])]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="auditoria.csv"'},
    )


# --- the whole instance (administrator) --------------------------------------------------


@router.get("/instance", response_model=AuditPage)
async def list_instance_events(
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
    actor_user_id: Optional[uuid.UUID] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    action: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    conditions = _filters(
        workspace_id=None, date_from=date_from, date_to=date_to, actor_user_id=actor_user_id,
        entity_type=entity_type, entity_id=entity_id, action=action,
    )
    return await _page(session, conditions, page, limit)


@router.get("/verify", response_model=AuditVerification)
async def verify_chain(
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    """Seal what is pending, then check every sealed row against the chain.

    `head_seq`/`head_hash` identify the newest sealed row: write them down somewhere the
    database's administrator cannot reach, and a later check can also catch rows removed
    from the end, which the chain alone cannot see.
    """
    await seal(session)
    checked, head_seq = (
        await session.execute(
            select(func.count(), func.max(AuditEvent.seq)).where(AuditEvent.hash.is_not(None))
        )
    ).one()
    head_hash = None
    if head_seq is not None:
        head_hash = (
            await session.execute(select(AuditEvent.hash).where(AuditEvent.seq == head_seq))
        ).scalar_one()
    broken = (await session.execute(text(VERIFY_QUERY))).first()
    if broken is None:
        return AuditVerification(ok=True, checked=checked, head_seq=head_seq, head_hash=head_hash)
    return AuditVerification(
        ok=False, checked=checked, head_seq=head_seq, head_hash=head_hash,
        broken_at_seq=broken.seq, reason=broken.reason,
    )
