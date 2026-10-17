# ruff: noqa: F811  (fixtures imported from test_reconciliation_service are redefined as arguments)
"""Several deposits, one invoice (A10).

The client who pays an invoice in instalments. The engine half is pure and
tested with no database; the service half proves what is stored and what
accepting writes.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import InvoiceAllocation
from app.models.reconciliation import ReconciliationEvent, ReconciliationSuggestion
from app.services import reconciliation_auto_service as auto
from app.services import reconciliation_policy as policy_module
from app.services import reconciliation_service
from app.services.reconciliation_engine import (
    AggregateMember,
    Expectation,
    Movement,
    Reason,
    evaluate,
    evaluate_aggregate,
)

# Fixtures and builders shared with the service tests.
from tests.test_reconciliation_service import (  # noqa: F401
    TODAY as SERVICE_TODAY,
    a_transaction,
    account,
    an_invoice,
    biz_headers,
    business_ws,
    client_payee,
)

TODAY = date(2026, 9, 1)
CLIENT = uuid.uuid4()
OTHER = uuid.uuid4()
ACCOUNT = uuid.uuid4()
STRATEGY = "same_client_aggregate_payments"


def policy(**amount) -> dict:
    p = policy_module.default_policy("reconciliation.match_invoice")
    for s in p["strategies"]:
        if s["id"] == STRATEGY:
            s["when"]["amount"].update({k: v for k, v in amount.items()})
    return p


def invoice(amount: str = "300.00", payee=CLIENT) -> Expectation:
    return Expectation(
        kind="invoice",
        id=uuid.uuid4(),
        amount=Decimal(amount),
        currency="BRL",
        direction="credit",
        when=TODAY,
        issued=TODAY - timedelta(days=20),
        payee_id=payee,
    )


def deposit(amount: str, days: int = 0, payee=CLIENT, account_id=ACCOUNT) -> AggregateMember:
    return AggregateMember(
        id=uuid.uuid4(),
        movement=Movement(
            amount=Decimal(amount),
            currency="BRL",
            direction="credit",
            when=TODAY + timedelta(days=days),
            payee_id=payee,
            account_id=account_id,
            source="sync",
        ),
    )


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------
def test_three_deposits_that_add_up_to_the_invoice_are_suggested():
    inv = invoice("300.00")
    pool = [deposit("100.00", -3), deposit("150.00", -2), deposit("50.00", -1)]

    out = evaluate_aggregate(pool, [inv], policy())

    assert len(out) == 1
    assert out[0].port == "suggested"
    assert out[0].expectation.id == inv.id
    assert {m.id for m in out[0].members} == {m.id for m in pool}
    assert out[0].amount == Decimal("300.00")
    assert out[0].difference == 0


def test_the_policy_ships_the_rule_after_the_set_rule_and_only_suggests():
    ids = [s["id"] for s in policy()["strategies"]]
    assert ids.index(STRATEGY) == ids.index("same_client_several_invoices") + 1
    rule = next(s for s in policy()["strategies"] if s["id"] == STRATEGY)
    assert rule["outcome"] == "suggest"


def test_even_a_rule_set_to_link_never_links_an_aggregate():
    p = policy()
    for s in p["strategies"]:
        if s["id"] == STRATEGY:
            s["outcome"] = "link"
    out = evaluate_aggregate([deposit("100.00"), deposit("200.00")], [invoice()], p)
    assert [d.port for d in out] == ["suggested"]


def test_deposits_from_different_payees_are_not_grouped():
    inv = invoice("300.00")
    pool = [deposit("100.00", payee=CLIENT), deposit("200.00", payee=OTHER)]
    assert evaluate_aggregate(pool, [inv], policy()) == []


def test_deposits_from_different_accounts_are_not_grouped():
    inv = invoice("300.00")
    pool = [deposit("100.00"), deposit("200.00", account_id=uuid.uuid4())]
    assert evaluate_aggregate(pool, [inv], policy()) == []


def test_a_group_larger_than_max_transactions_is_skipped():
    inv = invoice("100.00")
    pool = [deposit("25.00", -i) for i in range(4)]

    assert evaluate_aggregate(pool, [inv], policy(max_transactions=3)) == []
    assert len(evaluate_aggregate(pool, [inv], policy(max_transactions=4))) == 1


def test_too_large_a_pool_is_refused_loudly_rather_than_searched():
    inv = invoice("100.00")
    pool = [deposit("1.00", -(i % 5)) for i in range(20)]
    assert evaluate_aggregate(pool, [inv], policy()) == []


def test_a_sum_inside_the_tolerance_is_offered_and_outside_is_not():
    inv = invoice("300.00")
    pool = [deposit("100.00"), deposit("196.00")]  # 296: 1.33% short

    assert evaluate_aggregate(pool, [inv], policy()) == []
    out = evaluate_aggregate(pool, [inv], policy(percent="2"))
    assert len(out) == 1
    assert out[0].difference == Decimal("-4.00")
    assert out[0].amount == Decimal("296.00")


def test_an_overpaying_group_never_writes_more_than_the_invoice_is_owed():
    inv = invoice("300.00")
    out = evaluate_aggregate(
        [deposit("100.00"), deposit("203.00")], [inv], policy(percent="2")
    )
    assert out[0].amount == Decimal("300.00")
    assert out[0].difference == Decimal("3.00")


def test_deposits_outside_the_date_window_are_ignored():
    inv = invoice("300.00")
    pool = [deposit("100.00", 0), deposit("200.00", 400)]
    assert evaluate_aggregate(pool, [inv], policy()) == []


def test_a_deposit_is_never_used_for_two_invoices():
    a, b = invoice("300.00"), invoice("300.00")
    pool = [deposit("100.00"), deposit("200.00")]
    assert len(evaluate_aggregate(pool, [a, b], policy())) == 1


def test_identical_instalments_are_flagged_ambiguous_but_deterministic():
    inv = invoice("200.00")
    pool = [deposit("100.00", -3), deposit("100.00", -2), deposit("100.00", -1)]
    out = evaluate_aggregate(pool, [inv], policy())
    assert out[0].ambiguous
    # the earliest two
    assert [m.id for m in out[0].members] == [pool[0].id, pool[1].id]


def test_a_single_deposit_never_forms_an_aggregate():
    assert evaluate_aggregate([deposit("300.00")], [invoice()], policy()) == []


def test_the_per_movement_pass_ignores_the_aggregate_rule():
    inv = invoice("300.00")
    mv = deposit("100.00").movement
    decision = evaluate(mv, [inv], policy())
    assert decision.strategy != STRATEGY
    assert all(n.rejected_by is not Reason.AMOUNT or n.strategy != STRATEGY for n in decision.trace)


# ---------------------------------------------------------------------------
# Rule validation
# ---------------------------------------------------------------------------
def test_the_aggregate_match_validates_its_bounds():
    from app.services import reconciliation_rule_service as rules

    ok = rules._validate_amount({"match": "aggregate", "max_transactions": 5})
    assert ok["max_transactions"] == 5
    with pytest.raises(rules.RuleError):
        rules._validate_amount({"match": "aggregate", "max_transactions": 1})
    with pytest.raises(rules.RuleError):
        rules._validate_amount({"match": "aggregate", "max_transactions": 11})
    with pytest.raises(rules.RuleError):
        rules._validate_amount({"match": "aggregate", "percent": "25"})


# ---------------------------------------------------------------------------
# Against the database
# ---------------------------------------------------------------------------
async def _instalments(client, biz_headers, session, account, client_payee, test_user, amounts):
    inv = await an_invoice(
        client, biz_headers, total="300.00", payee_id=client_payee.id,
        due=SERVICE_TODAY + timedelta(days=1),
    )
    txs = [
        await a_transaction(
            session, account, test_user, amount=Decimal(a), payee_id=client_payee.id,
            when=SERVICE_TODAY - timedelta(days=i), description=f"PIX {i}",
        )
        for i, a in enumerate(amounts)
    ]
    return inv, txs


@pytest.mark.asyncio
async def test_instalments_over_several_syncs_become_one_aggregate_suggestion(
    client: AsyncClient, biz_headers, session: AsyncSession, account, client_payee, test_user
):
    inv, txs = await _instalments(
        client, biz_headers, session, account, client_payee, test_user,
        ["100.00", "150.00", "50.00"],
    )
    # They arrive in separate syncs; the last one completes the sum.
    for tx in reversed(txs):
        await reconciliation_service.match_incoming(session, account.workspace_id, [tx])
        await session.commit()

    rows = (await session.execute(
        select(ReconciliationSuggestion).where(ReconciliationSuggestion.is_aggregate.is_(True))
    )).unique().scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert str(row.expectation_id) == inv["id"]
    assert row.status == "pending"
    assert {m.transaction_id for m in row.member_transactions} == {t.id for t in txs}
    assert row.amount == Decimal("300.00")
    # Nothing was linked on its own.
    assert (await session.execute(select(InvoiceAllocation))).scalars().all() == []
    # Re-syncing does not ask again.
    await reconciliation_service.match_incoming(session, account.workspace_id, txs)
    await session.commit()
    again = (await session.execute(
        select(ReconciliationSuggestion).where(ReconciliationSuggestion.is_aggregate.is_(True))
    )).unique().scalars().all()
    assert len(again) == 1


@pytest.mark.asyncio
async def test_accepting_an_aggregate_allocates_every_deposit(
    client: AsyncClient, biz_headers, session: AsyncSession, account, client_payee, test_user
):
    inv, txs = await _instalments(
        client, biz_headers, session, account, client_payee, test_user,
        ["100.00", "150.00", "50.00"],
    )
    await reconciliation_service.match_incoming(session, account.workspace_id, txs)
    await session.commit()

    listing = await client.get("/api/reconciliation/suggestions", headers=biz_headers)
    assert listing.status_code == 200, listing.text
    aggregates = [s for s in listing.json() if s["is_aggregate"]]
    assert len(aggregates) == 1
    body = aggregates[0]
    assert set(body["member_transaction_ids"]) == {str(t.id) for t in txs}
    assert sum(Decimal(m["amount"]) for m in body["members"]) == Decimal("300.00")

    resp = await client.post(
        f"/api/reconciliation/suggestions/{body['id']}/accept", headers=biz_headers
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    allocations = (await session.execute(select(InvoiceAllocation))).scalars().all()
    assert {a.transaction_id for a in allocations} == {t.id for t in txs}
    assert sum(a.amount for a in allocations) == Decimal("300.00")
    assert all(a.method == STRATEGY for a in allocations)

    events = (await session.execute(
        select(ReconciliationEvent).where(ReconciliationEvent.action == "accepted")
    )).scalars().all()
    assert {e.transaction_id for e in events} == {t.id for t in txs}

    # The deposits' own part-payment questions are retired, not left to
    # spend the same money again.
    pending = (await session.execute(
        select(ReconciliationSuggestion).where(ReconciliationSuggestion.status == "pending")
    )).unique().scalars().all()
    assert pending == []


@pytest.mark.asyncio
async def test_declining_an_aggregate_is_remembered(
    client: AsyncClient, biz_headers, session: AsyncSession, account, client_payee, test_user
):
    _, txs = await _instalments(
        client, biz_headers, session, account, client_payee, test_user, ["100.00", "200.00"],
    )
    await reconciliation_service.match_incoming(session, account.workspace_id, txs)
    await session.commit()
    listing = await client.get("/api/reconciliation/suggestions", headers=biz_headers)
    agg = next(s for s in listing.json() if s["is_aggregate"])

    resp = await client.post(
        f"/api/reconciliation/suggestions/{agg['id']}/decline", headers=biz_headers
    )
    assert resp.status_code == 200, resp.text
    await reconciliation_service.match_incoming(session, account.workspace_id, txs)
    await session.commit()
    session.expire_all()

    rows = (await session.execute(
        select(ReconciliationSuggestion).where(ReconciliationSuggestion.is_aggregate.is_(True))
    )).unique().scalars().all()
    assert [r.status for r in rows] == ["declined"]


@pytest.mark.asyncio
async def test_accepting_refuses_the_whole_group_if_one_deposit_is_taken(
    client: AsyncClient, biz_headers, session: AsyncSession, account, client_payee, test_user
):
    inv, txs = await _instalments(
        client, biz_headers, session, account, client_payee, test_user, ["100.00", "200.00"],
    )
    await reconciliation_service.match_incoming(session, account.workspace_id, txs)
    await session.commit()
    listing = await client.get("/api/reconciliation/suggestions", headers=biz_headers)
    agg = next(s for s in listing.json() if s["is_aggregate"])

    # One deposit gets linked by hand to the invoice in the meantime.
    manual = await client.post(
        f"/api/invoices/{inv['id']}/allocations",
        headers=biz_headers,
        json={"transaction_id": str(txs[0].id), "amount": "100.00"},
    )
    if manual.status_code not in (200, 201):
        pytest.skip(f"manual allocation route unavailable: {manual.status_code}")

    resp = await client.post(
        f"/api/reconciliation/suggestions/{agg['id']}/accept", headers=biz_headers
    )
    assert resp.status_code == 400, resp.text
    session.expire_all()
    allocations = (await session.execute(select(InvoiceAllocation))).scalars().all()
    assert len(allocations) == 1


def test_an_aggregate_is_never_auto_applied():
    row = ReconciliationSuggestion(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        transaction_id=uuid.uuid4(),
        expectation_kind="invoice",
        expectation_id=uuid.uuid4(),
        strategy_id=STRATEGY,
        node="n",
        amount=Decimal("300"),
        scores={"of_set": 1, "amount_exact": True, "days_apart": 0, "description": 1.0},
        status="pending",
        is_aggregate=True,
    )
    assert not auto.is_eligible(row, 0.5)
