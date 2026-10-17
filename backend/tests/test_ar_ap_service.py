"""Tests for the consolidated AP/AR overview service.

Exercises `ar_ap_service.get_overview` against a real PostgreSQL database,
following the same session/workspace fixture pattern as `test_invoice_service.py`.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.workspace import Workspace, WorkspaceMember
from app.services import ar_ap_service
from app.services import invoice_service as inv_svc

pytestmark = pytest.mark.asyncio

TODAY = date.today()


# ---------------------------------------------------------------------------
# Fixtures — scoped to this module so they don't pollute the global conftest
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def workspace(session: AsyncSession, test_user) -> Workspace:
    ws = Workspace(
        id=uuid.uuid4(),
        name="Empresa Teste",
        kind="business",
        created_by_user_id=test_user.id,
    )
    session.add(ws)
    await session.flush()
    session.add(
        WorkspaceMember(
            id=uuid.uuid4(), workspace_id=ws.id, user_id=test_user.id, role="owner"
        )
    )
    await session.commit()
    return ws


# ---------------------------------------------------------------------------
# Local helpers — avoid depending on non-existent tests.factories module
# ---------------------------------------------------------------------------
async def _make_invoice(
    session: AsyncSession,
    workspace: Workspace,
    user,
    *,
    direction: str = "receivable",
    total: Decimal = Decimal("1000"),
    due_date=None,
) -> object:
    """Create and persist an open invoice via the service layer.

    `issue_date` is set to 30 days before `due_date` so that overdue
    invoices (due_date in the past) are always valid — the ledger requires
    due_date >= issue_date.
    """
    if due_date is None:
        due_date = TODAY + timedelta(days=10)
    issue_date = due_date - timedelta(days=30)
    invoice = await inv_svc.create_invoice(
        session,
        workspace.id,
        user.id,
        {
            "total": total,
            "issue_date": issue_date,
            "due_date": due_date,
            "direction": direction,
        },
    )
    await session.commit()
    return invoice


async def _make_allocation(
    session: AsyncSession,
    workspace: Workspace,
    user,
    invoice,
    amount: Decimal,
) -> object:
    """Create a Transaction and bind it to the invoice as an allocation.

    The FK on `InvoiceAllocation.transaction_id` requires a real transaction
    row, so we create a minimal account + transaction pair here.
    """
    account = Account(
        id=uuid.uuid4(),
        user_id=user.id,
        workspace_id=workspace.id,
        name="Conta Pagamentos",
        type="checking",
        currency="USD",
        balance=Decimal("0"),
    )
    session.add(account)
    await session.flush()

    tx = Transaction(
        id=uuid.uuid4(),
        user_id=user.id,
        workspace_id=workspace.id,
        account_id=account.id,
        description="Pagamento",
        amount=amount,
        currency="USD",
        date=TODAY,
        type="credit",
        source="manual",
    )
    session.add(tx)
    await session.flush()

    allocation = await inv_svc.allocate(session, invoice, tx.id, amount)
    await session.commit()
    return allocation


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_overview_empty(session: AsyncSession, workspace, test_user):
    """An empty workspace returns zeros on both sides and net_position zero."""
    result = await ar_ap_service.get_overview(session, workspace.id)
    assert result.receivable.outstanding == Decimal("0")
    assert result.payable.outstanding == Decimal("0")
    assert result.net_position == Decimal("0")


async def test_overview_accounts_both_sides(session: AsyncSession, workspace, test_user):
    """Outstanding and overdue figures are computed independently per direction."""
    # Receivable: R$ 1.000 a vencer
    await _make_invoice(
        session, workspace, test_user,
        direction="receivable",
        total=Decimal("1000"),
        due_date=TODAY + timedelta(days=10),
    )
    # Payable: R$ 300 vencida há 5 dias
    await _make_invoice(
        session, workspace, test_user,
        direction="payable",
        total=Decimal("300"),
        due_date=TODAY - timedelta(days=5),
    )

    result = await ar_ap_service.get_overview(session, workspace.id)

    assert result.receivable.outstanding == Decimal("1000")
    assert result.payable.outstanding == Decimal("300")
    assert result.payable.overdue_count == 1
    assert result.net_position == Decimal("700")  # 1000 - 300


async def test_overview_excludes_paid_invoices(session: AsyncSession, workspace, test_user):
    """A fully-allocated invoice must not appear in outstanding figures."""
    inv = await _make_invoice(
        session, workspace, test_user,
        direction="receivable",
        total=Decimal("500"),
        due_date=TODAY + timedelta(days=5),
    )
    await _make_allocation(session, workspace, test_user, inv, Decimal("500"))

    result = await ar_ap_service.get_overview(session, workspace.id)
    assert result.receivable.outstanding == Decimal("0")
