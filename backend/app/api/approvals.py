"""REST endpoints for the approvals workflow.

Pending transactions queue, approve/reject/cancel actions, and the
workspace approval-rules CRUD (threshold configuration).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete as _delete
from sqlalchemy import select as _select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, current_workspace, require_permission
from app.models.approval import WorkspaceApprovalRule
from app.schemas.approval import (
    ApprovalActionRequest,
    ApprovalRuleCreate,
    ApprovalRuleRead,
    ThresholdResponse,
)
from app.schemas.transaction import TransactionRead
from app.services import approval_service

# --- Dependency gates --------------------------------------------------------
# Declared at module level so `permission_gate` appears in every route's
# dependency graph — required by test_write_permission_coverage.
_approve_gate = require_permission("approvals.approve")
_write_gate = require_permission("transactions.write")
_manage_gate = require_permission("workspace.manage")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/approvals",
    tags=["approvals"],
)

rules_router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/approval-rules",
    tags=["approvals"],
)

Session = Annotated[AsyncSession, Depends(get_async_session)]


# --- Pending queue -----------------------------------------------------------
# NOTE: literal-path routes ("pending", "threshold") MUST come before any
# parameterised route (/{transaction_id}/*) so FastAPI doesn't swallow them
# as path parameters.

@router.get("/pending", response_model=list[TransactionRead])
async def list_pending(
    workspace_id: uuid.UUID,  # path param — routing only; ctx.workspace.id is authoritative
    session: Session,
    ctx: WorkspaceContext = Depends(_approve_gate),
) -> list[TransactionRead]:
    """List all transactions currently pending approval for this workspace."""
    return await approval_service.list_pending(session, ctx.workspace.id)


@router.get("/threshold", response_model=ThresholdResponse)
async def get_threshold(
    workspace_id: uuid.UUID,  # path param — routing only
    session: Session,
    ctx: WorkspaceContext = Depends(current_workspace),
    amount: Decimal = Query(..., description="Amount to test against the threshold"),
    category_group_id: Optional[uuid.UUID] = Query(default=None),
) -> ThresholdResponse:
    """Check whether a given amount would require approval under the current rules."""
    threshold = await approval_service.check_threshold(
        session, ctx.workspace.id, amount, category_group_id
    )
    needs = threshold is not None and abs(amount) > threshold
    return ThresholdResponse(
        threshold=threshold,
        currency="BRL" if threshold is not None else None,
        needs_approval=needs,
    )


# --- Per-transaction actions -------------------------------------------------

@router.post("/{transaction_id}/approve", response_model=TransactionRead)
async def approve_transaction(
    workspace_id: uuid.UUID,  # path param — routing only
    transaction_id: uuid.UUID,
    data: ApprovalActionRequest,
    session: Session,
    ctx: WorkspaceContext = Depends(_approve_gate),
) -> TransactionRead:
    """Approve a pending transaction.  The creator may not approve their own."""
    tx = await approval_service.approve(
        session, transaction_id, ctx.workspace.id, ctx.user_id, data.note
    )
    await session.commit()
    return tx


@router.post("/{transaction_id}/reject", response_model=TransactionRead)
async def reject_transaction(
    workspace_id: uuid.UUID,  # path param — routing only
    transaction_id: uuid.UUID,
    data: ApprovalActionRequest,
    session: Session,
    ctx: WorkspaceContext = Depends(_approve_gate),
) -> TransactionRead:
    """Reject a pending transaction."""
    tx = await approval_service.reject(
        session, transaction_id, ctx.workspace.id, ctx.user_id, data.note
    )
    await session.commit()
    return tx


@router.post("/{transaction_id}/settle", response_model=TransactionRead)
async def settle_transaction(
    workspace_id: uuid.UUID,  # path param — routing only
    transaction_id: uuid.UUID,
    data: ApprovalActionRequest,
    session: Session,
    ctx: WorkspaceContext = Depends(_approve_gate),
) -> TransactionRead:
    """Settle an approved transaction (confirm payment was made).

    When segregation of duties is enabled, the settler must differ from
    the creator and the approver.
    """
    tx = await approval_service.settle(
        session, transaction_id, ctx.workspace.id, ctx.user_id, data.note
    )
    await session.commit()
    return tx


@router.post("/{transaction_id}/cancel", response_model=TransactionRead)
async def cancel_transaction(
    workspace_id: uuid.UUID,  # path param — routing only
    transaction_id: uuid.UUID,
    session: Session,
    ctx: WorkspaceContext = Depends(_write_gate),
) -> TransactionRead:
    """Cancel a pending transaction (creator only, via transactions.write)."""
    tx = await approval_service.cancel(
        session, transaction_id, ctx.workspace.id, ctx.user_id
    )
    await session.commit()
    return tx


# --- Approval rules CRUD -----------------------------------------------------

@rules_router.get("", response_model=list[ApprovalRuleRead])
async def list_rules(
    workspace_id: uuid.UUID,  # path param — routing only
    session: Session,
    ctx: WorkspaceContext = Depends(current_workspace),
) -> list[ApprovalRuleRead]:
    """List all approval-threshold rules for this workspace."""
    r = await session.execute(
        _select(WorkspaceApprovalRule).where(
            WorkspaceApprovalRule.workspace_id == ctx.workspace.id
        )
    )
    return list(r.scalars())


@rules_router.post("", response_model=ApprovalRuleRead, status_code=201)
async def create_rule(
    workspace_id: uuid.UUID,  # path param — routing only
    data: ApprovalRuleCreate,
    session: Session,
    ctx: WorkspaceContext = Depends(_manage_gate),
) -> ApprovalRuleRead:
    """Create a new approval-threshold rule (workspace.manage required)."""
    rule = WorkspaceApprovalRule(
        workspace_id=ctx.workspace.id,
        category_group_id=data.category_group_id,
        amount_threshold=data.amount_threshold,
        currency=data.currency,
        created_by_user_id=ctx.user_id,
    )
    session.add(rule)
    await session.flush()
    await session.commit()
    return rule


@rules_router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    workspace_id: uuid.UUID,  # path param — routing only
    rule_id: uuid.UUID,
    session: Session,
    ctx: WorkspaceContext = Depends(_manage_gate),
) -> None:
    """Delete an approval-threshold rule (workspace.manage required)."""
    await session.execute(
        _delete(WorkspaceApprovalRule).where(
            WorkspaceApprovalRule.id == rule_id,
            WorkspaceApprovalRule.workspace_id == ctx.workspace.id,
        )
    )
    await session.commit()
