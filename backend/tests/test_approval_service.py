"""Tests for approval_service: threshold detection, submit, approve, reject, cancel."""
import datetime
import uuid as _uuid

import bcrypt as _bcrypt
import pytest
from decimal import Decimal
from sqlalchemy import select

from app.models.account import Account
from app.models.approval import ApprovalEvent, WorkspaceApprovalRule
from app.models.category import Category
from app.models.category_group import CategoryGroup
from app.models.transaction import Transaction
from app.models.user import User
from app.services import approval_service
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Local fixture: minimal account (no bank connection needed)
# ---------------------------------------------------------------------------

@pytest.fixture
async def approval_account(session, test_user, test_workspace):
    """A bare-minimum checking account for approval tests."""
    acc = Account(
        id=_uuid.uuid4(),
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        name="Conta Aprovação",
        type="checking",
        currency="BRL",
    )
    session.add(acc)
    await session.flush()
    return acc


# ---------------------------------------------------------------------------
# Helper to build a minimal Transaction
# ---------------------------------------------------------------------------

def _tx(test_user, test_workspace, account, amount, **kwargs):
    return Transaction(
        id=_uuid.uuid4(),
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        account_id=account.id,
        amount=amount,
        type=kwargs.pop("type", "debit"),
        date=kwargs.pop("date", datetime.date(2026, 1, 1)),
        description=kwargs.pop("description", "tx"),
        source=kwargs.pop("source", "manual"),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_rules_means_no_approval_needed(session, test_workspace, test_user, approval_account):
    tx = _tx(test_user, test_workspace, approval_account, Decimal("99999"))
    session.add(tx)
    await session.flush()
    assert await approval_service.needs_approval(session, test_workspace.id, tx) is False


@pytest.mark.asyncio
async def test_global_threshold_triggers_approval(session, test_workspace, test_user, approval_account):
    session.add(WorkspaceApprovalRule(
        workspace_id=test_workspace.id,
        category_group_id=None,
        amount_threshold=Decimal("1000"),
        currency="BRL",
        created_by_user_id=test_user.id,
    ))
    await session.flush()
    tx = _tx(test_user, test_workspace, approval_account, Decimal("1500"), description="Big tx")
    session.add(tx)
    await session.flush()
    assert await approval_service.needs_approval(session, test_workspace.id, tx) is True


@pytest.mark.asyncio
async def test_below_threshold_no_approval(session, test_workspace, test_user, approval_account):
    session.add(WorkspaceApprovalRule(
        workspace_id=test_workspace.id,
        category_group_id=None,
        amount_threshold=Decimal("1000"),
        currency="BRL",
        created_by_user_id=test_user.id,
    ))
    await session.flush()
    tx = _tx(test_user, test_workspace, approval_account, Decimal("500"), description="Small tx")
    session.add(tx)
    await session.flush()
    assert await approval_service.needs_approval(session, test_workspace.id, tx) is False


@pytest.mark.asyncio
async def test_group_threshold_overrides_global(session, test_workspace, test_user, approval_account):
    group = CategoryGroup(
        id=_uuid.uuid4(),
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        name="Despesas",
        natureza="despesa",
    )
    session.add(group)
    await session.flush()

    cat = Category(
        id=_uuid.uuid4(),
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        name="Viagem",
        group_id=group.id,
    )
    session.add(cat)

    # Global rule: R$1000; group rule: R$500
    session.add(WorkspaceApprovalRule(
        workspace_id=test_workspace.id,
        category_group_id=None,
        amount_threshold=Decimal("1000"),
        currency="BRL",
        created_by_user_id=test_user.id,
    ))
    session.add(WorkspaceApprovalRule(
        workspace_id=test_workspace.id,
        category_group_id=group.id,
        amount_threshold=Decimal("500"),
        currency="BRL",
        created_by_user_id=test_user.id,
    ))
    await session.flush()

    tx = _tx(test_user, test_workspace, approval_account, Decimal("700"),
             description="Trip", category_id=cat.id)
    session.add(tx)
    await session.flush()

    # 700 > 500 (group threshold) → needs approval
    assert await approval_service.needs_approval(session, test_workspace.id, tx) is True


@pytest.mark.asyncio
async def test_submit_sets_pending_status(session, test_workspace, test_user, approval_account):
    tx = _tx(test_user, test_workspace, approval_account, Decimal("2000"), description="Pending tx")
    session.add(tx)
    await session.flush()

    await approval_service.submit_for_approval(session, tx, test_user.id)

    assert tx.approval_status == "pending"
    events = await session.execute(
        select(ApprovalEvent).where(ApprovalEvent.transaction_id == tx.id)
    )
    assert events.scalars().first().action == "submitted"


@pytest.mark.asyncio
async def test_approve_sets_approved(session, test_workspace, test_user, approval_account):
    hashed = _bcrypt.hashpw(b"pass", _bcrypt.gensalt()).decode()
    approver = User(
        id=_uuid.uuid4(),
        email="approver@x.com",
        hashed_password=hashed,
        is_active=True,
        is_verified=True,
    )
    session.add(approver)

    tx = _tx(test_user, test_workspace, approval_account, Decimal("2000"),
             approval_status="pending")
    session.add(tx)
    await session.flush()

    result = await approval_service.approve(
        session, tx.id, test_workspace.id, approver.id, "OK"
    )
    assert result.approval_status == "approved"


@pytest.mark.asyncio
async def test_creator_cannot_approve_own_transaction(session, test_workspace, test_user, approval_account):
    tx = _tx(test_user, test_workspace, approval_account, Decimal("2000"),
             approval_status="pending")
    session.add(tx)
    await session.flush()

    with pytest.raises(HTTPException) as exc:
        await approval_service.approve(
            session, tx.id, test_workspace.id, test_user.id, None
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_reject_sets_rejected(session, test_workspace, test_user, approval_account):
    hashed = _bcrypt.hashpw(b"pass", _bcrypt.gensalt()).decode()
    approver = User(
        id=_uuid.uuid4(),
        email="approver2@x.com",
        hashed_password=hashed,
        is_active=True,
        is_verified=True,
    )
    session.add(approver)

    tx = _tx(test_user, test_workspace, approval_account, Decimal("2000"),
             approval_status="pending")
    session.add(tx)
    await session.flush()

    result = await approval_service.reject(
        session, tx.id, test_workspace.id, approver.id, "Não autorizado"
    )
    assert result.approval_status == "rejected"


@pytest.mark.asyncio
async def test_cancel_sets_rejected(session, test_workspace, test_user, approval_account):
    tx = _tx(test_user, test_workspace, approval_account, Decimal("2000"), approval_status="pending")
    session.add(tx)
    await session.flush()
    result = await approval_service.cancel(session, tx.id, test_workspace.id, test_user.id)
    assert result.approval_status == "rejected"
    events = (await session.execute(
        select(ApprovalEvent).where(ApprovalEvent.transaction_id == tx.id)
    )).scalars().all()
    assert any(e.action == "cancelled" for e in events)


@pytest.mark.asyncio
async def test_non_creator_cannot_cancel(session, test_workspace, test_user, approval_account):
    hashed = _bcrypt.hashpw(b"pass", _bcrypt.gensalt()).decode()
    other = User(id=_uuid.uuid4(), email="other@x.com", hashed_password=hashed,
                 is_active=True, is_verified=True)
    session.add(other)
    tx = _tx(test_user, test_workspace, approval_account, Decimal("500"), approval_status="pending")
    session.add(tx)
    await session.flush()
    with pytest.raises(HTTPException) as exc:
        await approval_service.cancel(session, tx.id, test_workspace.id, other.id)
    assert exc.value.status_code == 403
