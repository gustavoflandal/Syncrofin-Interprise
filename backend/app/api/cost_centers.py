import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, current_workspace, require_permission
from app.schemas.cost_center import CostCenterCreate, CostCenterRead, CostCenterUpdate
from app.services import cost_center_service

# Cost-center management is workspace configuration: only owners/managers may
# create, rename or deactivate them. Viewers may list them (current_workspace).
_manage_gate = require_permission("workspace.manage")

router = APIRouter(prefix="/api/cost-centers", tags=["cost-centers"])


@router.get("", response_model=list[CostCenterRead])
async def list_cost_centers(
    include_inactive: bool = Query(False, description="Include deactivated cost centers"),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await cost_center_service.list_cost_centers(
        session, ctx.workspace.id, include_inactive=include_inactive
    )


@router.post("", response_model=CostCenterRead, status_code=status.HTTP_201_CREATED)
async def create_cost_center(
    data: CostCenterCreate,
    ctx: WorkspaceContext = Depends(_manage_gate),
    session: AsyncSession = Depends(get_async_session),
):
    return await cost_center_service.create_cost_center(session, ctx.workspace.id, data)


@router.patch("/{cc_id}", response_model=CostCenterRead)
async def update_cost_center(
    cc_id: uuid.UUID,
    data: CostCenterUpdate,
    ctx: WorkspaceContext = Depends(_manage_gate),
    session: AsyncSession = Depends(get_async_session),
):
    cc = await cost_center_service.update_cost_center(session, cc_id, ctx.workspace.id, data)
    if not cc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centro de custo não encontrado")
    return cc


@router.delete("/{cc_id}")
async def delete_cost_center(
    cc_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_manage_gate),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        result = await cost_center_service.delete_cost_center(session, cc_id, ctx.workspace.id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Centro de custo não encontrado")
    if result is None:
        # Hard-deleted (was not in use)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    # Soft-deactivated (was in use)
    return result
