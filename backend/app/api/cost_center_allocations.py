import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, current_workspace, require_permission
from app.schemas.transaction import CostCenterAllocationRead, CostCenterAllocationWrite
from app.services import cost_center_allocation_service as svc

_write_gate = require_permission("transactions.write")

router = APIRouter(prefix="/api/transactions", tags=["cost-center-allocations"])


@router.get("/{transaction_id}/allocations", response_model=list[CostCenterAllocationRead])
async def list_allocations(
    transaction_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await svc.get_allocations(session, transaction_id, ctx.workspace.id)


@router.put("/{transaction_id}/allocations", response_model=list[CostCenterAllocationRead])
async def set_allocations(
    transaction_id: uuid.UUID,
    data: list[CostCenterAllocationWrite],
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    return await svc.set_allocations(
        session, transaction_id, ctx.workspace.id, [a.model_dump() for a in data]
    )


@router.delete("/{transaction_id}/allocations", status_code=status.HTTP_204_NO_CONTENT)
async def clear_allocations(
    transaction_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    await svc.clear_allocations(session, transaction_id, ctx.workspace.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
