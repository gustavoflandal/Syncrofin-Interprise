"""REST endpoints for period-close management.

Closing a period prevents new transactions from being entered or changed in
that year/month.  Only owners and roles with ``periods.manage`` may close or
reopen periods; any workspace member may list them.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, current_workspace, require_permission
from app.schemas.period_close import PeriodCloseCreate, PeriodCloseRead, PeriodReopenRequest
from app.services import period_close_service

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/period-closes",
    tags=["period-closes"],
)

Session = Annotated[AsyncSession, Depends(get_async_session)]

# Gate for mutating routes — only owners/roles with `periods.manage` may
# close or reopen a period.  Declaring this as a dependency (rather than
# calling ctx.require() inline) makes `permission_gate` appear in the
# dependency graph and satisfies test_write_permission_coverage.
_manage_gate = require_permission("periods.manage")


@router.get("", response_model=list[PeriodCloseRead])
async def list_period_closes(
    workspace_id: uuid.UUID,  # path param — routing only; ctx.workspace.id is authoritative
    session: Session,
    ctx: WorkspaceContext = Depends(current_workspace),
) -> list[PeriodCloseRead]:
    """Return all period-close records for the workspace, newest first."""
    return await period_close_service.list_period_closes(session, ctx.workspace.id)


@router.post("", response_model=PeriodCloseRead, status_code=201)
async def close_period(
    workspace_id: uuid.UUID,  # path param — routing only; ctx.workspace.id is authoritative
    data: PeriodCloseCreate,
    session: Session,
    ctx: WorkspaceContext = Depends(_manage_gate),
) -> PeriodCloseRead:
    """Close a period.  Returns 409 if the period is already closed."""
    return await period_close_service.close_period(
        session, ctx.workspace.id, ctx.user_id, data.year, data.month, data.reason
    )


@router.delete("/{year}/{month}", response_model=PeriodCloseRead)
async def reopen_period(
    workspace_id: uuid.UUID,  # path param — routing only; ctx.workspace.id is authoritative
    year: int,
    month: int,
    data: PeriodReopenRequest,
    session: Session,
    ctx: WorkspaceContext = Depends(_manage_gate),
) -> PeriodCloseRead:
    """Reopen a previously closed period.  Returns 404 if the period is not closed."""
    return await period_close_service.reopen_period(
        session, ctx.workspace.id, ctx.user_id, year, month, data.reason
    )
