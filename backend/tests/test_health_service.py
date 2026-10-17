"""Financial health score and cash-flow forecast."""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.invoice import Invoice
from app.models.transaction import Transaction
from app.models.user import User
from app.models.workspace import Workspace
from app.services import health_service as hs


# ---------------------------------------------------------------------------
# Pure rules
# ---------------------------------------------------------------------------
def must(component):
    """The component, asserted to exist (the rules return None for 'no verdict')."""
    assert component is not None
    return component


def test_savings_component_targets_twenty_percent():
    on_target = must(hs.savings_component(Decimal("1000"), Decimal("800")))
    assert on_target["value"] == 0.2 and on_target["score"] == 100
    half = must(hs.savings_component(Decimal("1000"), Decimal("900")))
    assert half["score"] == 50
    assert must(hs.savings_component(Decimal("1000"), Decimal("1200")))["score"] == 0  # clamped
    assert hs.savings_component(Decimal("0"), Decimal("10")) is None  # no income: no verdict


def test_reserve_component_targets_six_months():
    assert must(hs.reserve_component(Decimal("6000"), Decimal("1000")))["score"] == 100
    assert must(hs.reserve_component(Decimal("3000"), Decimal("1000")))["score"] == 50
    assert must(hs.reserve_component(Decimal("-500"), Decimal("1000")))["score"] == 0
    assert hs.reserve_component(Decimal("1000"), Decimal("0")) is None


def test_budget_component_is_the_share_within_limit():
    assert must(hs.budget_component(3, 4))["score"] == 75
    assert hs.budget_component(0, 0) is None


def test_combine_renormalises_missing_components():
    both = [
        {"key": "savings", "score": 100.0},
        {"key": "reserve", "score": 0.0},
    ]
    assert hs.combine(both) == (50, "attention")
    assert hs.combine([{"key": "budget", "score": 90.0}]) == (90, "good")
    assert hs.combine([]) == (None, "unknown")


def test_levels():
    assert hs.combine([{"key": "savings", "score": 80.0}])[1] == "good"
    assert hs.combine([{"key": "savings", "score": 60.0}])[1] == "attention"
    assert hs.combine([{"key": "savings", "score": 10.0}])[1] == "risk"


def test_add_months_crosses_year_boundaries():
    assert hs.add_months(date(2026, 1, 1), -3) == date(2025, 10, 1)
    assert hs.add_months(date(2026, 11, 1), 3) == date(2027, 2, 1)


def test_bucketize_runs_a_balance_and_treats_overdue_as_due_today():
    start = date(2026, 3, 2)
    events = [
        hs._Event(date(2026, 2, 20), Decimal("500"), "vencida", "invoice"),  # before start
        hs._Event(date(2026, 3, 10), Decimal("-300"), "aluguel", "recurring"),
        hs._Event(date(2026, 3, 30), Decimal("-2000"), "folha", "recurring"),
        hs._Event(date(2027, 1, 1), Decimal("999"), "longe", "invoice"),  # past horizon
    ]
    buckets = hs.bucketize(Decimal("1000"), events, start, days=35)

    assert len(buckets) == 5
    assert buckets[0].inflow == Decimal("500")          # overdue counted on day one
    assert buckets[0].balance == Decimal("1500")
    assert buckets[1].outflow == Decimal("300")
    assert buckets[1].balance == Decimal("1200")
    assert buckets[3].balance == Decimal("1200")
    assert buckets[4].balance == Decimal("-800")        # the payroll week goes negative
    assert sum(b.inflow for b in buckets) == Decimal("500")  # the far event was dropped


def test_bucketize_last_bucket_is_clipped_to_the_horizon():
    buckets = hs.bucketize(Decimal("0"), [], date(2026, 3, 2), days=10)
    assert [(b.start.day, b.end.day) for b in buckets] == [(2, 8), (9, 11)]


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
async def _tx(session, user, account, when, amount, typ, currency="BRL"):
    session.add(
        Transaction(
            id=uuid.uuid4(),
            user_id=user.id,
            account_id=account.id,
            description="t",
            amount=Decimal(amount),
            currency=currency,
            date=when,
            type=typ,
            source="manual",
            created_at=datetime.now(timezone.utc),
        )
    )


@pytest.mark.asyncio
async def test_health_without_data_has_no_score(
    client: AsyncClient, auth_headers, test_user: User
):
    response = await client.get("/api/dashboard/financial-health", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["score"] is None
    assert body["level"] == "unknown"
    assert body["components"] == []


@pytest.mark.asyncio
async def test_health_scores_savings_and_reserve(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers,
    test_user: User,
    test_account: Account,
):
    # Three complete months: income 1000, spending 800 each -> 20 % saved.
    first = hs.month_start(date.today())
    for back in (1, 2, 3):
        month = hs.add_months(first, -back)
        await _tx(session, test_user, test_account, month.replace(day=5), "1000", "credit")
        await _tx(session, test_user, test_account, month.replace(day=6), "800", "debit")
    test_account.balance = Decimal("4800")  # 6 months of 800
    test_account.currency = "BRL"
    await session.commit()

    response = await client.get("/api/dashboard/financial-health", headers=auth_headers)
    body = response.json()
    parts = {c["key"]: c for c in body["components"]}

    assert parts["savings"]["value"] == 0.2
    assert parts["savings"]["score"] == 100
    assert parts["reserve"]["value"] == 6.0
    assert body["score"] == 100 and body["level"] == "good"
    assert body["avg_monthly_income"] == 1000.0
    assert body["avg_monthly_expenses"] == 800.0
    assert body["liquid_balance"] == 4800.0


@pytest.mark.asyncio
async def test_a_manual_account_balance_is_the_sum_of_its_transactions(
    session: AsyncSession, test_user: User, test_workspace: Workspace
):
    """The `accounts.balance` column is not kept current for manual accounts.

    Reading it made the forecast start from zero however much money the account
    held: it was found running the real stack, not by the unit tests, which set
    the column directly on a *connected* account (where it is the truth).
    """
    manual = Account(
        id=uuid.uuid4(), user_id=test_user.id, name="Manual", type="checking",
        balance=Decimal("0.00"), currency="BRL",  # the stale column
    )
    session.add(manual)
    await session.flush()
    await _tx(session, test_user, manual, date.today(), "9000", "credit")
    await _tx(session, test_user, manual, date.today(), "1500", "debit")
    await session.commit()

    assert await hs.liquid_balance(session, test_workspace.id, "BRL") == Decimal("7500")


@pytest.mark.asyncio
async def test_a_future_dated_transaction_is_not_in_todays_balance(
    session: AsyncSession, test_user: User, test_workspace: Workspace
):
    manual = Account(
        id=uuid.uuid4(), user_id=test_user.id, name="Manual", type="checking",
        balance=Decimal("0.00"), currency="BRL",
    )
    session.add(manual)
    await session.flush()
    await _tx(session, test_user, manual, date.today(), "1000", "credit")
    await _tx(session, test_user, manual, date.today() + timedelta(days=5), "800", "debit")
    await session.commit()

    assert await hs.liquid_balance(session, test_workspace.id, "BRL") == Decimal("1000")


@pytest.mark.asyncio
async def test_credit_cards_are_not_liquid(
    session: AsyncSession, test_user: User, test_workspace: Workspace, test_account: Account
):
    test_account.currency = "BRL"
    test_account.balance = Decimal("1000")
    card = Account(
        id=uuid.uuid4(),
        user_id=test_user.id,
        name="Cartão",
        type="credit_card",
        balance=Decimal("-3000"),
        currency="BRL",
    )
    session.add(card)
    await session.commit()

    assert await hs.liquid_balance(session, test_workspace.id, "BRL") == Decimal("1000")


@pytest.mark.asyncio
async def test_foreign_currency_accounts_are_left_out_without_a_conversion(
    session: AsyncSession, test_user: User, test_workspace: Workspace, test_account: Account
):
    test_account.currency = "EUR"
    test_account.balance = Decimal("1000")
    test_account.balance_primary = None
    await session.commit()
    assert await hs.liquid_balance(session, test_workspace.id, "BRL") == Decimal("0")

    test_account.balance_primary = Decimal("6000")
    await session.commit()
    assert await hs.liquid_balance(session, test_workspace.id, "BRL") == Decimal("6000")


@pytest.mark.asyncio
async def test_forecast_defaults_and_bounds(client: AsyncClient, auth_headers, test_user: User):
    response = await client.get("/api/dashboard/cash-flow-forecast", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["buckets"]) == 13  # 90 days in weeks
    assert body["first_negative_week_start"] is None
    assert body["assumptions"]["excludes"]

    assert (
        await client.get(
            "/api/dashboard/cash-flow-forecast", params={"days": 3}, headers=auth_headers
        )
    ).status_code == 422


async def _invoice(session, user, workspace, *, direction, total, due, number):
    invoice = Invoice(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        direction=direction,
        status="open",
        number=number,
        currency="BRL",
        subtotal=Decimal(total),
        total=Decimal(total),
        issue_date=date.today(),
        due_date=due,
    )
    session.add(invoice)
    return invoice


@pytest.mark.asyncio
async def test_forecast_uses_open_invoices_and_flags_the_first_negative_week(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers,
    test_user: User,
    test_workspace: Workspace,
    test_account: Account,
):
    test_account.currency = "BRL"
    test_account.balance = Decimal("1000")
    today = date.today()
    await _invoice(session, test_user, test_workspace, direction="receivable",
                   total="400", due=today + timedelta(days=3), number=1)
    await _invoice(session, test_user, test_workspace, direction="payable",
                   total="5000", due=today + timedelta(days=20), number=2)
    await session.commit()

    response = await client.get("/api/dashboard/cash-flow-forecast", headers=auth_headers)
    body = response.json()

    assert body["starting_balance"] == 1000.0
    assert body["net_by_source"]["invoice"] == -4600.0
    assert body["ending_balance"] == -3600.0
    assert body["lowest_balance"] == -3600.0
    assert body["first_negative_week_start"] is not None
    # the receivable lands in the first week, the payable in the third
    assert body["buckets"][0]["inflow"] == 400.0
    assert body["buckets"][2]["outflow"] == 5000.0


@pytest.mark.asyncio
async def test_overdue_receivables_show_up_in_health(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers,
    test_user: User,
    test_workspace: Workspace,
):
    await _invoice(session, test_user, test_workspace, direction="receivable",
                   total="750", due=date.today() - timedelta(days=10), number=7)
    await session.commit()

    body = (await client.get("/api/dashboard/financial-health", headers=auth_headers)).json()
    assert body["overdue_receivables"] == {"count": 1, "total": 750.0}
