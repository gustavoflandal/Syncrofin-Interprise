"""D2: data retention policy per workspace."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, require_permission
from app.schemas.data_retention import RetentionPolicyRead, RetentionPolicyUpdate
from app.services import data_retention_service

_manage_gate = require_permission("workspace.manage")

router = APIRouter(
    prefix="/api/data-retention",
    tags=["data-retention"],
)

Session = Annotated[AsyncSession, Depends(get_async_session)]


@router.get("/", response_model=RetentionPolicyRead)
async def get_policy(
    session: Session,
    ctx: WorkspaceContext = Depends(_manage_gate),
):
    """Get the current workspace retention policy (creates default if none)."""
    policy = await data_retention_service.get_policy(session, ctx.workspace.id)
    await session.commit()
    return policy


@router.patch("/", response_model=RetentionPolicyRead)
async def update_policy(
    body: RetentionPolicyUpdate,
    session: Session,
    ctx: WorkspaceContext = Depends(_manage_gate),
):
    """Update the workspace retention policy."""
    data = body.model_dump(exclude_unset=True)
    policy = await data_retention_service.update_policy(session, ctx.workspace.id, data)
    await session.commit()
    return policy


@router.post("/purge")
async def trigger_purge(
    session: Session,
    ctx: WorkspaceContext = Depends(_manage_gate),
):
    """Trigger a manual data retention purge for this workspace."""
    counts = await data_retention_service.purge_expired_data(session, ctx.workspace.id)
    await session.commit()
    return counts
