"""Tests for segregation of duties (C3).

Covers:
  - Creator cannot reject their own tx when segregation is enabled
  - Creator can reject their own tx when segregation is disabled
  - Settle by a third user succeeds
  - Settle by creator is blocked when segregation is on
  - Settle by approver is blocked when segregation is on
  - Settle requires approved status
"""
import datetime
import uuid as _uuid

import bcrypt as _bcrypt
import pytest
from decimal import Decimal
from sqlalchemy import select

from app.models.account import Account
from app.models.approval import ApprovalEvent
from app.models.transaction import Transaction
from app.models.user import User
from app.services import approval_service
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def segregation_account(session, test_user, test_workspace):
    """A bare-minimum checking account for segregation tests."""
    acc = Account(
        id=_uuid.uuid4(),
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        name="Conta Segregação",
        type="checking",
        currency="BRL",
    )
    session.add(acc)
    await session.flush()
    return acc


@pytest.fixture
async def approver_user(session):
    """A second user who will act as the approver."""
    hashed = _bcrypt.hashpw(b"pass", _bcrypt.gensalt()).decode()
    user = User(
        id=_uuid.uuid4(),
        email="approver_seg@x.com",
        hashed_password=hashed,
        is_active=True,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.fixture
async def settler_user(session):
    """A third user who will act as the settler."""
    hashed = _bcrypt.hashpw(b"pass", _bcrypt.gensalt()).decode()
    user = User(
        id=_uuid.uuid4(),
        email="settler_seg@x.com",
        hashed_password=hashed,
        is_active=True,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    return user


def _tx(user, workspace, account, amount, **kwargs):
    return Transaction(
        id=_uuid.uuid4(),
        user_id=user.id,
        workspace_id=workspace.id,
        account_id=account.id,
        amount=amount,
        type=kwargs.pop("type", "debit"),
        date=kwargs.pop("date", datetime.date(2026, 1, 1)),
        description=kwargs.pop("description", "tx-seg"),
        source=kwargs.pop("source", "manual"),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_creator_cannot_reject_own_with_segregation(
    session, test_user, test_workspace, segregation_account
):
    """With segregation on, the creator must cancel — not reject — their tx."""
    test_workspace.segregation_enabled = True
    await session.flush()

    tx = _tx(test_user, test_workspace, segregation_account, Decimal("2000"),
             approval_status="pending")
    session.add(tx)
    await session.flush()

    with pytest.raises(HTTPException) as exc:
        await approval_service.reject(
            session, tx.id, test_workspace.id, test_user.id, "tentativa"
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_creator_can_reject_own_without_segregation(
    session, test_user, test_workspace, segregation_account, approver_user
):
    """Without segregation the creator is allowed to reject (legacy behaviour)."""
    test_workspace.segregation_enabled = False
    await session.flush()

    tx = _tx(test_user, test_workspace, segregation_account, Decimal("2000"),
             approval_status="pending")
    session.add(tx)
    await session.flush()

    result = await approval_service.reject(
        session, tx.id, test_workspace.id, test_user.id, "ok"
    )
    assert result.approval_status == "rejected"


@pytest.mark.asyncio
async def test_settle_different_user(
    session, test_user, test_workspace, segregation_account,
    approver_user, settler_user,
):
    """Approve by one user, settle by a third → ok."""
    test_workspace.segregation_enabled = True
    await session.flush()

    tx = _tx(test_user, test_workspace, segregation_account, Decimal("5000"),
             approval_status="pending")
    session.add(tx)
    await session.flush()

    # Approve as approver_user
    await approval_service.approve(
        session, tx.id, test_workspace.id, approver_user.id, "aprovado"
    )

    # Settle as settler_user (third party)
    result = await approval_service.settle(
        session, tx.id, test_workspace.id, settler_user.id, "pago"
    )
    assert result.settled_by_user_id == settler_user.id
    assert result.settled_at is not None

    # Check approval event was created
    events = (await session.execute(
        select(ApprovalEvent).where(
            ApprovalEvent.transaction_id == tx.id,
            ApprovalEvent.action == "settled",
        )
    )).scalars().all()
    assert len(events) == 1
    assert events[0].actor_user_id == settler_user.id


@pytest.mark.asyncio
async def test_settle_by_creator_blocked(
    session, test_user, test_workspace, segregation_account, approver_user,
):
    """Segregation on → creator cannot settle their own tx."""
    test_workspace.segregation_enabled = True
    await session.flush()

    tx = _tx(test_user, test_workspace, segregation_account, Decimal("3000"),
             approval_status="pending")
    session.add(tx)
    await session.flush()

    await approval_service.approve(
        session, tx.id, test_workspace.id, approver_user.id, None
    )

    with pytest.raises(HTTPException) as exc:
        await approval_service.settle(
            session, tx.id, test_workspace.id, test_user.id, "tentativa"
        )
    assert exc.value.status_code == 403
    assert "Creator" in exc.value.detail


@pytest.mark.asyncio
async def test_settle_by_approver_blocked(
    session, test_user, test_workspace, segregation_account, approver_user,
):
    """Segregation on → approver cannot settle the tx they approved."""
    test_workspace.segregation_enabled = True
    await session.flush()

    tx = _tx(test_user, test_workspace, segregation_account, Decimal("3000"),
             approval_status="pending")
    session.add(tx)
    await session.flush()

    await approval_service.approve(
        session, tx.id, test_workspace.id, approver_user.id, None
    )

    with pytest.raises(HTTPException) as exc:
        await approval_service.settle(
            session, tx.id, test_workspace.id, approver_user.id, "tentativa"
        )
    assert exc.value.status_code == 403
    assert "Approver" in exc.value.detail


@pytest.mark.asyncio
async def test_settle_requires_approved_status(
    session, test_user, test_workspace, segregation_account, settler_user,
):
    """Cannot settle a pending (not yet approved) transaction."""
    tx = _tx(test_user, test_workspace, segregation_account, Decimal("1000"),
             approval_status="pending")
    session.add(tx)
    await session.flush()

    with pytest.raises(HTTPException) as exc:
        await approval_service.settle(
            session, tx.id, test_workspace.id, settler_user.id
        )
    assert exc.value.status_code == 409
    assert "approved" in exc.value.detail.lower()
