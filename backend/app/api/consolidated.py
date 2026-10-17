"""Consolidated (multi-workspace) financial reports — A7.

Any authenticated user may query workspaces they are a member of.
The membership check is enforced in `consolidated_service.get_consolidated_dre`.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import current_active_user
from app.core.database import get_async_session
from app.models.user import User
from app.schemas.consolidated import ConsolidatedDreResponse
from app.services import consolidated_service

router = APIRouter(
    prefix="/api/consolidated",
    tags=["consolidated"],
)

Session = Annotated[AsyncSession, Depends(get_async_session)]


@router.get("/dre", response_model=ConsolidatedDreResponse)
async def consolidated_dre(
    workspace_ids: list[uuid.UUID] = Query(..., alias="workspace_id"),
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    accounting_mode: str = Query("competence", pattern="^(competence|cash)$"),
    session: Session = ...,
    user: User = Depends(current_active_user),
):
    """Consolidated DRE across the requested workspaces.

    - `workspace_id` may be repeated: `?workspace_id=<a>&workspace_id=<b>`
    - Requires membership in every listed workspace (403 otherwise).
    - Inter-company transfers are already excluded by the P&L filter.
    """
    if not workspace_ids:
        raise HTTPException(status_code=422, detail="At least one workspace_id is required")
    if len(workspace_ids) < 2:
        raise HTTPException(
            status_code=422,
            detail="Use the workspace DRE endpoint for a single workspace",
        )
    try:
        result = await consolidated_service.get_consolidated_dre(
            session,
            workspace_ids=workspace_ids,
            user_id=user.id,
            year=year,
            month=month,
            accounting_mode=accounting_mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return ConsolidatedDreResponse(
        year=result.year,
        month=result.month,
        workspace_reports=[
            {
                "workspace_id": ws.workspace_id,
                "workspace_name": ws.workspace_name,
                "currency": ws.currency,
                "dre": ws.dre,
            }
            for ws in result.workspace_reports
        ],
        consolidated=result.consolidated,
    )
