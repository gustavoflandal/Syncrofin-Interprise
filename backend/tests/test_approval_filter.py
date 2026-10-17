"""Tests for approval_status filtering in report_service and transaction_service.

Verifies that transactions with approval_status='pending' or 'rejected' are
excluded from financial report totals (DRE-like), and that get_transactions
respects the include_pending_approval flag.
"""
import datetime
import uuid as _uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.user import User
from app.services import report_service, transaction_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def filter_account(session, test_user, test_workspace):
    """A minimal checking account for approval-filter tests."""
    acc = Account(
        id=_uuid.uuid4(),
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        name="Conta Filtro Aprovação",
        type="checking",
        currency="BRL",
    )
    session.add(acc)
    await session.flush()
    return acc


def _make_tx(test_user, test_workspace, account, amount, txn_type="credit", **kwargs):
    """Helper to build a minimal posted Transaction row."""
    return Transaction(
        id=_uuid.uuid4(),
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        account_id=account.id,
        amount=Decimal(str(amount)),
        type=txn_type,
        date=datetime.date(2026, 3, 15),
        description=kwargs.pop("description", "test-tx"),
        source="manual",
        status="posted",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# report_service (DRE / get_dre) tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dre_excludes_pending_approval(session, test_user, test_workspace, filter_account):
    """A transaction with approval_status='pending' must NOT appear in DRE totals."""
    tx = _make_tx(
        test_user, test_workspace, filter_account,
        amount="500.00", txn_type="credit",
        description="pendente-aprovação",
        approval_status="pending",
    )
    session.add(tx)
    await session.flush()

    report = await report_service.get_dre(
        session, test_workspace.id, test_user.id,
        year=2026, month=3, include_prev=False,
    )

    # gross_revenue should be 0 because the only transaction is pending approval
    assert report.gross_revenue == Decimal("0"), (
        f"Expected gross_revenue=0 but got {report.gross_revenue}"
    )


@pytest.mark.asyncio
async def test_dre_excludes_rejected_approval(session, test_user, test_workspace, filter_account):
    """A transaction with approval_status='rejected' must NOT appear in DRE totals."""
    tx = _make_tx(
        test_user, test_workspace, filter_account,
        amount="300.00", txn_type="credit",
        description="rejeitado",
        approval_status="rejected",
    )
    session.add(tx)
    await session.flush()

    report = await report_service.get_dre(
        session, test_workspace.id, test_user.id,
        year=2026, month=3, include_prev=False,
    )

    assert report.gross_revenue == Decimal("0"), (
        f"Expected gross_revenue=0 but got {report.gross_revenue}"
    )


@pytest.mark.asyncio
async def test_dre_includes_approved(session, test_user, test_workspace, filter_account):
    """A transaction with approval_status='approved' MUST appear in DRE totals."""
    tx = _make_tx(
        test_user, test_workspace, filter_account,
        amount="1000.00", txn_type="credit",
        description="aprovado",
        approval_status="approved",
    )
    session.add(tx)
    await session.flush()

    report = await report_service.get_dre(
        session, test_workspace.id, test_user.id,
        year=2026, month=3, include_prev=False,
    )

    assert report.gross_revenue == Decimal("1000.00"), (
        f"Expected gross_revenue=1000 but got {report.gross_revenue}"
    )


@pytest.mark.asyncio
async def test_dre_includes_null_approval_status(session, test_user, test_workspace, filter_account):
    """A transaction with approval_status=NULL (no approval required) MUST appear in DRE totals."""
    tx = _make_tx(
        test_user, test_workspace, filter_account,
        amount="750.00", txn_type="credit",
        description="sem-aprovação",
        # approval_status intentionally omitted — defaults to None
    )
    session.add(tx)
    await session.flush()

    report = await report_service.get_dre(
        session, test_workspace.id, test_user.id,
        year=2026, month=3, include_prev=False,
    )

    assert report.gross_revenue == Decimal("750.00"), (
        f"Expected gross_revenue=750 but got {report.gross_revenue}"
    )


# ---------------------------------------------------------------------------
# transaction_service.get_transactions tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_transactions_excludes_pending_by_default(session, test_user, test_workspace, filter_account):
    """get_transactions with include_pending_approval=False (default) must exclude pending txs."""
    tx_pending = _make_tx(
        test_user, test_workspace, filter_account,
        amount="100.00", txn_type="debit",
        description="pendente",
        approval_status="pending",
    )
    tx_approved = _make_tx(
        test_user, test_workspace, filter_account,
        amount="200.00", txn_type="debit",
        description="aprovado",
        approval_status="approved",
    )
    tx_null = _make_tx(
        test_user, test_workspace, filter_account,
        amount="300.00", txn_type="debit",
        description="sem-status",
    )
    session.add_all([tx_pending, tx_approved, tx_null])
    await session.flush()

    txns, total, _ = await transaction_service.get_transactions(
        session=session,
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        account_id=filter_account.id,
        # include_pending_approval defaults to False
    )

    ids = {str(t.id) for t in txns}
    assert str(tx_pending.id) not in ids, "Pending-approval tx should be excluded by default"
    assert str(tx_approved.id) in ids, "Approved tx should be included"
    assert str(tx_null.id) in ids, "Null-status tx should be included"


@pytest.mark.asyncio
async def test_list_transactions_includes_pending_when_requested(session, test_user, test_workspace, filter_account):
    """get_transactions with include_pending_approval=True must include pending txs."""
    tx_pending = _make_tx(
        test_user, test_workspace, filter_account,
        amount="100.00", txn_type="debit",
        description="pendente-include",
        approval_status="pending",
    )
    session.add(tx_pending)
    await session.flush()

    txns, total, _ = await transaction_service.get_transactions(
        session=session,
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        account_id=filter_account.id,
        include_pending_approval=True,
    )

    ids = {str(t.id) for t in txns}
    assert str(tx_pending.id) in ids, "Pending-approval tx should be included when explicitly requested"
