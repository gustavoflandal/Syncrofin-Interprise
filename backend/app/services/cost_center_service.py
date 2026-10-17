import uuid
from typing import Optional

from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cost_center import CostCenter
from app.models.transaction import Transaction
from app.models.budget import Budget
from app.schemas.cost_center import CostCenterCreate, CostCenterUpdate


async def list_cost_centers(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    include_inactive: bool = False,
) -> list[CostCenter]:
    filters = [CostCenter.workspace_id == workspace_id]
    if not include_inactive:
        filters.append(CostCenter.is_active.is_(True))
    result = await session.execute(
        select(CostCenter).where(*filters).order_by(CostCenter.name)
    )
    return list(result.scalars().all())


async def get_cost_center(
    session: AsyncSession, cc_id: uuid.UUID, workspace_id: uuid.UUID
) -> Optional[CostCenter]:
    result = await session.execute(
        select(CostCenter).where(CostCenter.id == cc_id, CostCenter.workspace_id == workspace_id)
    )
    return result.scalar_one_or_none()


async def create_cost_center(
    session: AsyncSession, workspace_id: uuid.UUID, data: CostCenterCreate
) -> CostCenter:
    cc = CostCenter(workspace_id=workspace_id, **data.model_dump())
    session.add(cc)
    await session.commit()
    await session.refresh(cc)
    return cc


async def update_cost_center(
    session: AsyncSession, cc_id: uuid.UUID, workspace_id: uuid.UUID, data: CostCenterUpdate
) -> Optional[CostCenter]:
    cc = await get_cost_center(session, cc_id, workspace_id)
    if not cc:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(cc, key, value)
    await session.commit()
    await session.refresh(cc)
    return cc


async def _is_in_use(session: AsyncSession, cc_id: uuid.UUID) -> bool:
    in_tx = await session.scalar(
        select(exists().where(Transaction.cost_center_id == cc_id))
    )
    in_budget = await session.scalar(
        select(exists().where(Budget.cost_center_id == cc_id))
    )
    return bool(in_tx or in_budget)


async def delete_cost_center(
    session: AsyncSession, cc_id: uuid.UUID, workspace_id: uuid.UUID
) -> Optional[CostCenter]:
    """Hard-delete if unused; soft-deactivate if in use.

    Returns the deactivated CostCenter (in-use case) or None (deleted case).
    Raises KeyError("not_found") when the CC does not exist in the workspace.
    """
    cc = await get_cost_center(session, cc_id, workspace_id)
    if not cc:
        raise KeyError("not_found")
    if await _is_in_use(session, cc_id):
        cc.is_active = False
        await session.commit()
        await session.refresh(cc)
        return cc
    await session.delete(cc)
    await session.commit()
    return None
