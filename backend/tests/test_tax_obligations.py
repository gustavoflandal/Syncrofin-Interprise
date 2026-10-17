"""Tests for tax obligations (B3/T4)."""
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.schemas.recurring_transaction import RecurringTransactionCreate
from app.services.ar_ap_service import get_forecast
from app.services.invoice_service import create_invoice
from app.services.recurring_transaction_service import create_recurring_transaction


def _das(account_id: uuid.UUID, **extra) -> RecurringTransactionCreate:
    return RecurringTransactionCreate(
        description="DAS Simples Nacional",
        amount=Decimal("1200.00"),
        currency="BRL",
        type="debit",
        frequency="monthly",
        day_of_month=20,
        start_date=date(2026, 1, 1),
        account_id=account_id,
        tax_obligation_type="das",
        **extra,
    )


@pytest.mark.asyncio
async def test_create_tax_obligation_as_recurring(session, test_workspace, test_user, test_account):
    rt = await create_recurring_transaction(
        session, test_workspace.id, test_user.id,
        _das(test_account.id, competence_offset_months=1),
    )
    await session.commit()
    assert rt.tax_obligation_type == "das"
    assert rt.competence_offset_months == 1


@pytest.mark.asyncio
async def test_tax_obligations_in_ar_ap_forecast(session, test_workspace, test_user, test_account):
    await create_recurring_transaction(
        session, test_workspace.id, test_user.id, _das(test_account.id)
    )
    await session.commit()

    forecast = await get_forecast(
        session, test_workspace.id, currency="BRL", period="month",
        num_buckets=3, today=date(2026, 10, 1),
    )
    assert sum(b.taxes for b in forecast.buckets) >= Decimal("1200.00")
    first = forecast.buckets[0]
    assert first.net == first.receivable - first.payable - first.taxes


@pytest.mark.asyncio
async def test_receivable_forecast_uses_net_receivable(session, test_workspace, test_user):
    await create_invoice(
        session, test_workspace.id, test_user.id,
        {
            "direction": "receivable",
            "issue_date": date(2026, 10, 1),
            "due_date": date(2026, 10, 15),
            "currency": "BRL",
            "total": Decimal("10000.00"),
            "withholdings": [
                {"tax_type": "irrf", "base_amount": Decimal("10000.00"), "withheld_amount": Decimal("150.00")},
            ],
        },
    )
    await session.commit()

    forecast = await get_forecast(
        session, test_workspace.id, currency="BRL", period="month",
        num_buckets=1, today=date(2026, 10, 1),
    )
    assert forecast.buckets[0].receivable == Decimal("9850.00")


def test_withholding_ratios_br_returns_common_rates():
    """BR jurisdiction returns common withholding ratios."""
    from app.services.reconciliation_policy import withholding_ratios

    ratios = withholding_ratios("BR")
    assert len(ratios) > 0
    assert all(Decimal("0") < r < Decimal("1") for r in ratios)
    assert Decimal("0.985") in ratios  # IRRF 1.5%


def test_withholding_ratios_none_returns_empty():
    """No jurisdiction returns empty list."""
    from app.services.reconciliation_policy import withholding_ratios

    assert withholding_ratios(None) == []
    assert withholding_ratios("US") == []
