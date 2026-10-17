from __future__ import annotations
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.models.approval import WorkspaceApprovalRule, ApprovalEvent
from app.models.transaction import Transaction
from app.models.workspace import Workspace


async def get_threshold(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    transaction: Transaction,
) -> Optional[Decimal]:
    """Return the applicable threshold for this transaction, or None if no rule exists."""
    category_group_id: Optional[uuid.UUID] = None
    if transaction.category_id:
        from app.models.category import Category
        cat = await session.get(Category, transaction.category_id)
        if cat:
            category_group_id = cat.group_id

    # Try group-specific rule first
    if category_group_id:
        r = await session.execute(
            select(WorkspaceApprovalRule).where(
                WorkspaceApprovalRule.workspace_id == workspace_id,
                WorkspaceApprovalRule.category_group_id == category_group_id,
            )
        )
        rule = r.scalar_one_or_none()
        if rule:
            return rule.amount_threshold

    # Fallback: global rule (category_group_id IS NULL)
    r = await session.execute(
        select(WorkspaceApprovalRule).where(
            WorkspaceApprovalRule.workspace_id == workspace_id,
            WorkspaceApprovalRule.category_group_id.is_(None),
        )
    )
    rule = r.scalar_one_or_none()
    return rule.amount_threshold if rule else None


async def needs_approval(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    transaction: Transaction,
) -> bool:
    threshold = await get_threshold(session, workspace_id, transaction)
    if threshold is None:
        return False
    return abs(transaction.amount) > threshold


async def submit_for_approval(
    session: AsyncSession,
    transaction: Transaction,
    actor_user_id: uuid.UUID,
) -> None:
    transaction.approval_status = "pending"
    session.add(ApprovalEvent(
        transaction_id=transaction.id,
        actor_user_id=actor_user_id,
        action="submitted",
        occurred_at=datetime.now(timezone.utc),
    ))
    await session.flush()


async def approve(
    session: AsyncSession,
    transaction_id: uuid.UUID,
    workspace_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    note: Optional[str],
) -> Transaction:
    tx = await _get_pending(session, transaction_id, workspace_id)
    if tx.user_id == actor_user_id:
        raise HTTPException(status_code=403, detail="Creator cannot approve their own transaction")
    tx.approval_status = "approved"
    session.add(ApprovalEvent(
        transaction_id=tx.id,
        actor_user_id=actor_user_id,
        action="approved",
        note=note,
        occurred_at=datetime.now(timezone.utc),
    ))
    await session.flush()
    return tx


async def reject(
    session: AsyncSession,
    transaction_id: uuid.UUID,
    workspace_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    note: Optional[str],
) -> Transaction:
    tx = await _get_pending(session, transaction_id, workspace_id)
    # C3: when segregation is enabled the creator cannot reject their own
    # transaction — they should use cancel instead.
    if tx.user_id == actor_user_id:
        ws = await session.get(Workspace, workspace_id)
        if ws and ws.segregation_enabled:
            raise HTTPException(
                status_code=403,
                detail="Creator cannot reject their own transaction (use cancel instead)",
            )
    tx.approval_status = "rejected"
    session.add(ApprovalEvent(
        transaction_id=tx.id,
        actor_user_id=actor_user_id,
        action="rejected",
        note=note,
        occurred_at=datetime.now(timezone.utc),
    ))
    await session.flush()
    return tx


async def cancel(
    session: AsyncSession,
    transaction_id: uuid.UUID,
    workspace_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Transaction:
    r = await session.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.workspace_id == workspace_id,
            Transaction.approval_status == "pending",
        ).with_for_update()
    )
    tx = r.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=404, detail="Pending transaction not found")
    if tx.user_id != actor_user_id:
        raise HTTPException(status_code=403, detail="Only the creator can cancel")
    tx.approval_status = "cancelled"
    session.add(ApprovalEvent(
        transaction_id=tx.id,
        actor_user_id=actor_user_id,
        action="cancelled",
        occurred_at=datetime.now(timezone.utc),
    ))
    await session.flush()
    return tx


async def list_pending(
    session: AsyncSession,
    workspace_id: uuid.UUID,
) -> list[Transaction]:
    r = await session.execute(
        select(Transaction).where(
            Transaction.workspace_id == workspace_id,
            Transaction.approval_status == "pending",
        ).order_by(Transaction.date.desc())
    )
    return list(r.scalars())


async def check_threshold(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    amount: Decimal,
    category_group_id: Optional[uuid.UUID],
) -> Optional[Decimal]:
    """Return the applicable threshold for a given amount/group combo (for UI preview)."""
    if category_group_id:
        r = await session.execute(
            select(WorkspaceApprovalRule).where(
                WorkspaceApprovalRule.workspace_id == workspace_id,
                WorkspaceApprovalRule.category_group_id == category_group_id,
            )
        )
        rule = r.scalar_one_or_none()
        if rule:
            return rule.amount_threshold

    r = await session.execute(
        select(WorkspaceApprovalRule).where(
            WorkspaceApprovalRule.workspace_id == workspace_id,
            WorkspaceApprovalRule.category_group_id.is_(None),
        )
    )
    rule = r.scalar_one_or_none()
    return rule.amount_threshold if rule else None


async def settle(
    session: AsyncSession,
    transaction_id: uuid.UUID,
    workspace_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    note: Optional[str] = None,
) -> Transaction:
    """Mark an approved transaction as settled (payment confirmed).

    C3 segregation (when enabled): the settler must be a different person
    from both the creator and the approver.
    """
    r = await session.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.workspace_id == workspace_id,
        ).with_for_update()
    )
    tx = r.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if tx.approval_status != "approved":
        raise HTTPException(
            status_code=409,
            detail="Only approved transactions can be settled",
        )
    if tx.settled_by_user_id is not None:
        raise HTTPException(status_code=409, detail="Transaction already settled")

    ws = await session.get(Workspace, workspace_id)
    if ws and ws.segregation_enabled:
        can, reason = await check_can_settle(session, tx, actor_user_id, ws)
        if not can:
            raise HTTPException(status_code=403, detail=reason)

    tx.settled_by_user_id = actor_user_id
    tx.settled_at = datetime.now(timezone.utc)
    session.add(ApprovalEvent(
        transaction_id=tx.id,
        actor_user_id=actor_user_id,
        action="settled",
        note=note,
        occurred_at=datetime.now(timezone.utc),
    ))
    await session.flush()
    return tx


async def check_can_settle(
    session: AsyncSession,
    transaction: Transaction,
    actor_user_id: uuid.UUID,
    workspace: Workspace,
) -> tuple[bool, str]:
    """Return (can_settle, reason) for the frontend to enable/disable the button."""
    if not workspace.segregation_enabled:
        return True, ""
    if transaction.user_id == actor_user_id:
        return False, "Creator cannot settle their own transaction"
    # Check the approver
    r = await session.execute(
        select(ApprovalEvent).where(
            ApprovalEvent.transaction_id == transaction.id,
            ApprovalEvent.action == "approved",
        ).order_by(ApprovalEvent.occurred_at.desc()).limit(1)
    )
    approval_event = r.scalar_one_or_none()
    if approval_event and approval_event.actor_user_id == actor_user_id:
        return False, "Approver cannot settle the transaction they approved"
    return True, ""


async def _get_pending(
    session: AsyncSession,
    transaction_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Transaction:
    r = await session.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.workspace_id == workspace_id,
            Transaction.approval_status == "pending",
        ).with_for_update()
    )
    tx = r.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=404, detail="Pending transaction not found")
    return tx
