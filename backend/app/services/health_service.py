"""Financial health score and cash-flow forecast.

Two questions a person asks the dashboard and could not answer from it:

    "Am I okay?"            -> `get_financial_health`
    "Will I run out, when?" -> `get_cashflow_forecast`

**The score is deliberately boring.** Three components, each a plain ratio
with a stated target, combined by fixed weights. Anything cleverer would be
a number nobody can argue with, and a health score that cannot be argued
with is one people stop believing the first time it is wrong:

    poupança      taxa de poupança  = (receitas - despesas) / receitas   meta 20 %      peso 40
    reserva       meses de reserva  = saldo líquido / despesa média      meta 6 meses   peso 40
    orçamento     % das categorias com orçamento dentro do limite        meta 100 %     peso 20

Income and spending are averaged over the **last three complete months**:
the current month is unfinished, so its ratio would swing with the day of
the month. A component without data (no income, no budgets) is left out
and the remaining weights are renormalised, rather than scored as zero,
which would punish a workspace for something it has not set up.

**The forecast is a projection, not a prediction.** It walks forward from
today's liquid balance and adds only what is *already promised*: recurring
bills and open invoices. It does not guess at discretionary spending, so a
low point in the chart is "you will be here if nothing else happens", which
is the useful reading for a treasurer and the honest one.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.invoice import Invoice
from app.models.transaction import Transaction
from app.models.user import User
from app.services import budget_service, dashboard_service, invoice_service
from app.services._query_filters import counts_as_user_pnl

ZERO = Decimal("0")

#: Targets. Conventional planning rules of thumb, kept as named constants so
#: they are visible, testable and easy to make configurable later.
SAVINGS_TARGET = Decimal("0.20")
RESERVE_TARGET_MONTHS = Decimal("6")

WEIGHTS = {"savings": 40, "reserve": 40, "budget": 20}

#: Account types whose balance is money you can spend. A credit card's
#: "balance" is debt, and counting it as cash would flatter the score.
LIQUID_TYPES = ("checking", "savings", "wallet")


# ---------------------------------------------------------------------------
# Small pure helpers (unit-tested directly)
# ---------------------------------------------------------------------------
def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def savings_component(income: Decimal, expenses: Decimal) -> Optional[dict]:
    if income <= ZERO:
        return None
    rate = (income - expenses) / income
    return {
        "key": "savings",
        "value": float(round(rate, 4)),
        "target": float(SAVINGS_TARGET),
        "score": round(_clamp(float(rate / SAVINGS_TARGET) * 100), 1),
    }


def reserve_component(liquid: Decimal, monthly_expenses: Decimal) -> Optional[dict]:
    if monthly_expenses <= ZERO:
        return None
    months = max(liquid, ZERO) / monthly_expenses
    return {
        "key": "reserve",
        "value": float(round(months, 2)),
        "target": float(RESERVE_TARGET_MONTHS),
        "score": round(_clamp(float(months / RESERVE_TARGET_MONTHS) * 100), 1),
    }


def budget_component(within: int, total: int) -> Optional[dict]:
    if total <= 0:
        return None
    share = within / total
    return {
        "key": "budget",
        "value": float(round(share, 4)),
        "target": 1.0,
        "score": round(share * 100, 1),
    }


def combine(components: list[dict]) -> tuple[Optional[int], str]:
    """Weighted mean of the components that exist. `None` when none do."""
    if not components:
        return None, "unknown"
    total_weight = sum(WEIGHTS[c["key"]] for c in components)
    score = sum(c["score"] * WEIGHTS[c["key"]] for c in components) / total_weight
    score = int(round(score))
    level = "good" if score >= 75 else "attention" if score >= 50 else "risk"
    return score, level


def status_for(score: float) -> str:
    return "good" if score >= 75 else "attention" if score >= 50 else "risk"


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    idx = d.year * 12 + (d.month - 1) + n
    return date(idx // 12, idx % 12 + 1, 1)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
async def _primary_currency(session: AsyncSession, user_id: uuid.UUID) -> str:
    from app.core.config import get_settings

    user = await session.get(User, user_id)
    return (user.primary_currency if user else None) or get_settings().default_currency


async def liquid_balance(
    session: AsyncSession, workspace_id: uuid.UUID, primary_currency: str
) -> Decimal:
    """Spendable money in the main currency: open cash accounts only.

    "Balance" is not the `accounts.balance` column. For a **manual** account that
    column is not kept current; the balance is the sum of its transactions. For a
    **connected** account the provider's figure is the truth. The dashboard already
    knows both rules (`_account_balance_at`), so this asks it rather than
    re-deriving them: a second copy of "what is my balance" is how two screens
    end up showing different numbers.

    An account in another currency counts through its stored primary balance,
    scaled to today's figure; without one it is left out rather than added at
    face value, because "1,000 EUR" is not "1,000 BRL".
    """
    today = date.today()
    accounts = await dashboard_service._get_open_accounts(session, workspace_id)
    total = ZERO
    for account in accounts:
        if account.type not in LIQUID_TYPES:
            continue
        current = Decimal(str(await dashboard_service._account_balance_at(session, account, today)))
        if account.currency == primary_currency:
            total += current
        elif account.balance_primary is not None and account.balance:
            total += current * Decimal(account.balance_primary) / Decimal(account.balance)
    return total


async def _month_totals(
    session: AsyncSession, workspace_id: uuid.UUID, start: date, end: date
) -> tuple[Decimal, Decimal]:
    """(income, expenses) posted in [start, end), main currency, P&L only."""
    amt = func.coalesce(Transaction.amount_primary, Transaction.amount)
    rows = (
        await session.execute(
            select(Transaction.type, func.sum(amt))
            .where(
                Transaction.workspace_id == workspace_id,
                Transaction.date >= start,
                Transaction.date < end,
                Transaction.status == "posted",
                Transaction.source != "opening_balance",
                counts_as_user_pnl(),
            )
            .group_by(Transaction.type)
        )
    ).all()
    income = expenses = ZERO
    for kind, total in rows:
        value = abs(Decimal(total or 0))
        if kind == "credit":
            income = value
        else:
            expenses = value
    return income, expenses


# ---------------------------------------------------------------------------
# Financial health
# ---------------------------------------------------------------------------
async def get_financial_health(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    today: Optional[date] = None,
) -> dict:
    today = today or date.today()
    primary = await _primary_currency(session, user_id)

    # Three complete months before the current one.
    window_start = add_months(month_start(today), -3)
    window_end = month_start(today)
    income, expenses = await _month_totals(session, workspace_id, window_start, window_end)
    avg_income, avg_expenses = income / 3, expenses / 3

    liquid = await liquid_balance(session, workspace_id, primary)

    budgets = await budget_service.get_budget_vs_actual(session, workspace_id, user_id, today)
    # (row, limit) pairs, so the limit is a plain Decimal from here on.
    budgeted = [(b, b.budget_amount) for b in budgets if b.budget_amount and b.budget_amount > 0]
    within = sum(1 for b, limit in budgeted if b.actual_amount <= limit)

    components = [
        c
        for c in (
            savings_component(income, expenses),
            reserve_component(liquid, avg_expenses),
            budget_component(within, len(budgeted)),
        )
        if c is not None
    ]
    for c in components:
        c["status"] = status_for(c["score"])
    score, level = combine(components)

    overdue = await _overdue_receivables(session, workspace_id, primary, today)

    return {
        "score": score,
        "level": level,
        "primary_currency": primary,
        "components": components,
        "avg_monthly_income": float(round(avg_income, 2)),
        "avg_monthly_expenses": float(round(avg_expenses, 2)),
        "liquid_balance": float(round(liquid, 2)),
        "over_budget": [
            {"category_id": str(b.category_id), "category_name": b.category_name,
             "budget": float(limit), "actual": float(b.actual_amount)}
            for b, limit in budgeted
            if b.actual_amount > limit
        ],
        "overdue_receivables": overdue,
        "months_analysed": 3,
    }


async def _overdue_receivables(
    session: AsyncSession, workspace_id: uuid.UUID, primary: str, today: date
) -> dict:
    invoices = (
        await session.execute(
            select(Invoice)
            .where(
                Invoice.workspace_id == workspace_id,
                Invoice.direction == "receivable",
                Invoice.status == "open",
                Invoice.currency == primary,
                Invoice.due_date < today,
            )
            .options(selectinload(Invoice.allocations))
        )
    ).scalars().all()
    total = ZERO
    count = 0
    for inv in invoices:
        remaining = invoice_service.balance(inv)
        if remaining > ZERO:
            total += remaining
            count += 1
    return {"count": count, "total": float(round(total, 2))}


# ---------------------------------------------------------------------------
# Cash-flow forecast
# ---------------------------------------------------------------------------
@dataclass
class _Event:
    when: date
    amount: Decimal  # signed: inflow +, outflow -
    label: str
    source: str  # recurring | invoice


@dataclass
class _Bucket:
    start: date
    end: date
    inflow: Decimal = ZERO
    outflow: Decimal = ZERO
    balance: Decimal = ZERO
    events: list = field(default_factory=list)


def bucketize(
    start_balance: Decimal, events: list[_Event], start: date, days: int, bucket_days: int = 7
) -> list[_Bucket]:
    """Fold events into fixed-width buckets with a running balance.

    Pure so it can be tested without a database. Events dated before `start`
    are treated as due today (an overdue receivable is money you are still
    waiting for, not money that vanished), and events past the horizon are
    dropped.
    """
    end = start + timedelta(days=days)
    buckets: list[_Bucket] = []
    cursor = start
    while cursor < end:
        nxt = min(cursor + timedelta(days=bucket_days), end)
        buckets.append(_Bucket(start=cursor, end=nxt - timedelta(days=1)))
        cursor = nxt

    for ev in sorted(events, key=lambda e: e.when):
        when = max(ev.when, start)
        if when >= end:
            continue
        for b in buckets:
            if b.start <= when <= b.end:
                if ev.amount >= ZERO:
                    b.inflow += ev.amount
                else:
                    b.outflow += -ev.amount
                b.events.append(ev)
                break

    running = start_balance
    for b in buckets:
        running += b.inflow - b.outflow
        b.balance = running
    return buckets


async def _recurring_events(
    session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID, start: date, end: date
) -> list[_Event]:
    projected = await dashboard_service.get_projected_transactions(
        session, workspace_id, user_id, from_date=start, to_date=end
    )
    events = []
    for p in projected:
        amount = Decimal(str(p.amount_primary if p.amount_primary is not None else p.amount))
        amount = abs(amount)
        events.append(
            _Event(
                when=date.fromisoformat(p.date),
                amount=amount if p.type == "credit" else -amount,
                label=p.description,
                source="recurring",
            )
        )
    return events


async def _invoice_events(
    session: AsyncSession, workspace_id: uuid.UUID, primary: str, end: date
) -> list[_Event]:
    invoices = (
        await session.execute(
            select(Invoice)
            .where(
                Invoice.workspace_id == workspace_id,
                Invoice.status == "open",
                Invoice.currency == primary,
                Invoice.due_date <= end,
            )
            .options(selectinload(Invoice.allocations))
        )
    ).scalars().all()
    events = []
    for inv in invoices:
        remaining = invoice_service.balance(inv)
        if remaining <= ZERO:
            continue
        signed = remaining if inv.direction == "receivable" else -remaining
        label = f"#{inv.number}" if inv.number else "Fatura"
        events.append(_Event(when=inv.due_date, amount=signed, label=label, source="invoice"))
    return events


async def get_cashflow_forecast(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    days: int = 90,
    today: Optional[date] = None,
) -> dict:
    today = today or date.today()
    primary = await _primary_currency(session, user_id)
    start_balance = await liquid_balance(session, workspace_id, primary)
    end = today + timedelta(days=days)

    events = await _recurring_events(session, workspace_id, user_id, today, end)
    events += await _invoice_events(session, workspace_id, primary, end)
    buckets = bucketize(start_balance, events, today, days)

    low = min(buckets, key=lambda b: b.balance) if buckets else None
    first_negative = next((b for b in buckets if b.balance < ZERO), None)

    by_source: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for ev in events:
        by_source[ev.source] += ev.amount

    return {
        "primary_currency": primary,
        "start_date": today.isoformat(),
        "end_date": end.isoformat(),
        "starting_balance": float(round(start_balance, 2)),
        "ending_balance": float(round(buckets[-1].balance, 2)) if buckets else float(start_balance),
        "lowest_balance": float(round(low.balance, 2)) if low else float(start_balance),
        "lowest_balance_week_start": low.start.isoformat() if low else None,
        "first_negative_week_start": first_negative.start.isoformat() if first_negative else None,
        "net_by_source": {k: float(round(v, 2)) for k, v in by_source.items()},
        "buckets": [
            {
                "start": b.start.isoformat(),
                "end": b.end.isoformat(),
                "inflow": float(round(b.inflow, 2)),
                "outflow": float(round(b.outflow, 2)),
                "balance": float(round(b.balance, 2)),
                "events": len(b.events),
            }
            for b in buckets
        ],
        "assumptions": {
            "includes": ["recurring", "open_invoices"],
            "excludes": ["discretionary_spending", "credit_card_bills", "foreign_currency_invoices"],
        },
    }
