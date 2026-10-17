from __future__ import annotations
import uuid
from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.models.period_close import PeriodClose
from app.models.workspace import Workspace


async def _dispatch_webhook(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    event_type: str,
    year: int,
    month: int,
) -> None:
    try:
        from app.services import webhook_service as _whs
        await _whs.dispatch_event(session, workspace_id, event_type, {"year": year, "month": month})
        await session.commit()
    except Exception:
        pass


async def is_period_closed(
    session: AsyncSession,
    workspace: Workspace,
    tx_date: date,
    effective_date: Optional[date] = None,
) -> bool:
    """Return True if the period containing `tx_date` (or `effective_date` when configured) is closed."""
    check_date = (
        effective_date if workspace.period_close_by == "effective_date" and effective_date is not None
        else tx_date
    )
    result = await session.execute(
        select(PeriodClose).where(
            PeriodClose.workspace_id == workspace.id,
            PeriodClose.year == check_date.year,
            PeriodClose.month == check_date.month,
            PeriodClose.reopened_at.is_(None),
        )
    )
    return result.scalar_one_or_none() is not None


async def close_period(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    year: int,
    month: int,
    reason: Optional[str],
) -> PeriodClose:
    # Look up any existing record for this workspace/year/month, regardless of reopened_at.
    # A reopened record can be re-closed; a still-closed record raises 409.
    result = await session.execute(
        select(PeriodClose).where(
            PeriodClose.workspace_id == workspace_id,
            PeriodClose.year == year,
            PeriodClose.month == month,
        )
    )
    pc = result.scalar_one_or_none()

    if pc is not None:
        if pc.reopened_at is None:
            # Already closed and never reopened (or re-closed already)
            raise HTTPException(status_code=409, detail="Period is already closed")
        # Re-close after reopen: reset reopen fields and update close metadata
        pc.reopened_at = None
        pc.reopened_by_user_id = None
        pc.reopen_reason = None
        pc.closed_at = datetime.now(timezone.utc)
        pc.closed_by_user_id = user_id
        pc.reason = reason
        await session.commit()
        await _dispatch_webhook(session, workspace_id, "period.closed", year, month)
        return pc

    # First close: create a new record
    pc = PeriodClose(
        workspace_id=workspace_id,
        year=year,
        month=month,
        closed_by_user_id=user_id,
        closed_at=datetime.now(timezone.utc),
        reason=reason,
    )
    session.add(pc)
    await session.commit()
    await _dispatch_webhook(session, workspace_id, "period.closed", year, month)
    return pc


async def reopen_period(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    year: int,
    month: int,
    reason: Optional[str],
) -> PeriodClose:
    result = await session.execute(
        select(PeriodClose).where(
            PeriodClose.workspace_id == workspace_id,
            PeriodClose.year == year,
            PeriodClose.month == month,
            PeriodClose.reopened_at.is_(None),
        )
    )
    pc = result.scalar_one_or_none()
    if not pc:
        raise HTTPException(status_code=404, detail="Closed period not found")

    pc.reopened_at = datetime.now(timezone.utc)
    pc.reopened_by_user_id = user_id
    pc.reopen_reason = reason
    await session.commit()
    await _dispatch_webhook(session, workspace_id, "period.reopened", year, month)
    return pc


async def list_period_closes(
    session: AsyncSession,
    workspace_id: uuid.UUID,
) -> list[PeriodClose]:
    result = await session.execute(
        select(PeriodClose)
        .where(PeriodClose.workspace_id == workspace_id)
        .order_by(PeriodClose.year.desc(), PeriodClose.month.desc())
    )
    return list(result.scalars())
