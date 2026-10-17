"""Integration tests for period-close and approval guards in transaction_service."""
import pytest
import datetime
from decimal import Decimal
from datetime import date
from fastapi import HTTPException
from app.models.account import Account
from app.models.approval import WorkspaceApprovalRule
from app.schemas.transaction import TransactionCreate, TransactionUpdate
from app.services import transaction_service, period_close_service


@pytest.mark.asyncio
async def test_create_in_closed_period_raises_422(session, test_workspace, test_user):
    """Creating a transaction whose date falls in a closed period must raise HTTP 422."""
    account = Account(
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        name="Conta Guard 1",
        type="checking",
        currency="BRL",
    )
    session.add(account)
    await session.flush()

    # Close January 2026 – close_period commits internally
    await period_close_service.close_period(
        session, test_workspace.id, test_user.id, 2026, 1, None
    )

    data = TransactionCreate(
        account_id=account.id,
        amount=Decimal("100"),
        type="debit",
        date=date(2026, 1, 15),
        description="tx em período fechado",
    )
    with pytest.raises(HTTPException) as exc:
        await transaction_service.create_transaction(
            session, test_workspace.id, test_user.id, data
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "period_closed"
    assert exc.value.detail["period"] == "2026-01"


@pytest.mark.asyncio
async def test_create_in_open_period_succeeds(session, test_workspace, test_user):
    """Creating a transaction in an open period must succeed without approval."""
    account = Account(
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        name="Conta Guard 2",
        type="checking",
        currency="BRL",
    )
    session.add(account)
    await session.flush()

    data = TransactionCreate(
        account_id=account.id,
        amount=Decimal("100"),
        type="debit",
        date=date(2026, 2, 1),
        description="tx em período aberto",
    )
    tx = await transaction_service.create_transaction(
        session, test_workspace.id, test_user.id, data
    )
    assert tx.id is not None
    assert tx.approval_status is None


@pytest.mark.asyncio
async def test_update_from_closed_period_via_date_change_raises_422(
    session, test_workspace, test_user
):
    """Moving a transaction OUT of a closed period must also be rejected.

    Bypass scenario: transaction lives in Jan/2026 (closed). Caller sends
    PATCH {"date": "2026-02-01"} — without checking the *origin* date the
    guard would see only Feb (open) and allow the edit, silently mutating a
    record that belongs to a frozen period. The fix checks both sides.
    """
    account = Account(
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        name="Conta Guard 4",
        type="checking",
        currency="BRL",
    )
    session.add(account)
    await session.flush()

    # Close January 2026 (commits internally).
    await period_close_service.close_period(
        session, test_workspace.id, test_user.id, 2026, 1, None
    )

    # Insert the transaction directly (bypassing the create guard) so it
    # lands in the already-closed January period.
    from app.models.transaction import Transaction
    tx = Transaction(
        workspace_id=test_workspace.id,
        account_id=account.id,
        amount=Decimal("100.00"),
        date=datetime.date(2026, 1, 15),
        description="tx em jan fechado",
        type="credit",
        user_id=test_user.id,
        currency="BRL",
        source="manual",
        status="posted",
    )
    session.add(tx)
    await session.commit()

    # Try to move it to February — must be rejected because the *origin*
    # period (January) is closed, regardless of the destination being open.
    with pytest.raises(HTTPException) as exc:
        await transaction_service.update_transaction(
            session,
            tx.id,
            test_workspace.id,
            test_user.id,
            TransactionUpdate(date=datetime.date(2026, 2, 1)),
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "period_closed"
    assert "2026-01" in exc.value.detail["period"]


@pytest.mark.asyncio
async def test_create_above_threshold_sets_pending(session, test_workspace, test_user):
    """A transaction whose amount exceeds the workspace approval threshold must be set to 'pending'."""
    rule = WorkspaceApprovalRule(
        workspace_id=test_workspace.id,
        amount_threshold=Decimal("500"),
        currency="BRL",
        created_by_user_id=test_user.id,
    )
    session.add(rule)
    account = Account(
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        name="Conta Guard 3",
        type="checking",
        currency="BRL",
    )
    session.add(account)
    await session.flush()

    data = TransactionCreate(
        account_id=account.id,
        amount=Decimal("1000"),
        type="debit",
        date=date(2026, 2, 1),
        description="transação grande",
    )
    tx = await transaction_service.create_transaction(
        session, test_workspace.id, test_user.id, data
    )
    assert tx.approval_status == "pending"
