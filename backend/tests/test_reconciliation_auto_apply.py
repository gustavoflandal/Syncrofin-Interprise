"""Accepting the suggestions the engine is confident about."""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.invoice import Invoice, InvoiceAllocation
from app.models.reconciliation import ReconciliationEvent, ReconciliationSuggestion
from app.models.transaction import Transaction
from app.models.user import User
from app.models.workspace import Workspace
from app.services import reconciliation_auto_service as auto


async def _get(session, model, ident):
    """A row that must exist, typed so its attributes can be read."""
    obj = await session.get(model, ident)
    assert obj is not None
    return obj


def _row(**scores) -> ReconciliationSuggestion:
    base = {"of_set": 1, "amount_exact": True, "days_apart": 2, "description": 0.95}
    base.update(scores)
    return ReconciliationSuggestion(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        transaction_id=uuid.uuid4(),
        expectation_kind="invoice",
        expectation_id=uuid.uuid4(),
        strategy_id="s",
        node="n",
        amount=Decimal("300"),
        scores=base,
        status="pending",
    )


# ---------------------------------------------------------------------------
# The bar, alone
# ---------------------------------------------------------------------------
def test_a_confident_exact_match_clears_the_bar():
    assert auto.is_eligible(_row(), 0.9)


def test_the_description_score_must_reach_the_workspace_bar():
    assert not auto.is_eligible(_row(description=0.85), 0.9)
    assert auto.is_eligible(_row(description=0.9), 0.9)  # inclusive


def test_a_near_miss_on_the_amount_is_a_humans_call():
    assert not auto.is_eligible(_row(amount_exact=False, description=1.0), 0.5)


def test_a_payment_far_from_the_due_date_is_left_alone():
    assert auto.is_eligible(_row(days_apart=7), 0.9)
    assert not auto.is_eligible(_row(days_apart=8), 0.9)
    assert not auto.is_eligible(_row(days_apart=-30), 0.9)  # early is as suspect as late


def test_one_payment_against_several_invoices_is_never_automatic():
    assert not auto.is_eligible(_row(of_set=3), 0.5)
    grouped = _row()
    grouped.group_id = uuid.uuid4()
    assert not auto.is_eligible(grouped, 0.5)


def test_only_pending_rows_qualify():
    done = _row()
    done.status = "declined"
    assert not auto.is_eligible(done, 0.5)


def test_missing_or_garbled_scores_do_not_qualify():
    assert not auto.is_eligible(_row(description="n/a"), 0.5)
    bare = _row()
    bare.scores = {}
    assert not auto.is_eligible(bare, 0.5)


# ---------------------------------------------------------------------------
# Against a real invoice
# ---------------------------------------------------------------------------
async def _setup(session, user, workspace, account, *, paid=Decimal("300"), **scores):
    invoice = Invoice(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        direction="receivable",
        status="open",
        number=1,
        currency="BRL",
        subtotal=Decimal("300"),
        total=Decimal("300"),
        issue_date=date.today() - timedelta(days=10),
        due_date=date.today() - timedelta(days=1),
    )
    tx = Transaction(
        id=uuid.uuid4(),
        user_id=user.id,
        account_id=account.id,
        description="PIX CLIENTE",
        amount=paid,
        currency="BRL",
        date=date.today(),
        type="credit",
        source="manual",
        created_at=datetime.now(timezone.utc),
    )
    session.add_all([invoice, tx])
    await session.flush()
    suggestion = _row(**scores)
    suggestion.workspace_id = workspace.id
    suggestion.transaction_id = tx.id
    suggestion.expectation_id = invoice.id
    suggestion.amount = paid
    session.add(suggestion)
    await session.commit()
    ids = (invoice.id, tx.id, suggestion.id)
    # Hand the service objects it loads itself, as in production: instances
    # built in this session have unloaded collections that cannot lazy-load.
    session.expunge_all()
    return ids


@pytest.mark.asyncio
async def test_auto_apply_settles_the_invoice_and_leaves_a_system_trail(
    session: AsyncSession, test_user: User, test_workspace: Workspace, test_account: Account
):
    invoice_id, _, suggestion_id = await _setup(session, test_user, test_workspace, test_account)

    result = await auto.auto_apply(session, test_workspace.id, Decimal("0.90"))
    await session.commit()

    assert (result.applied, result.skipped, result.failed) == (1, 0, 0)
    suggestion = await _get(session, ReconciliationSuggestion, suggestion_id)
    await session.refresh(suggestion)
    assert suggestion.status == "accepted"
    assert suggestion.resolved_by is None  # the system, not a person

    allocations = (
        await session.execute(select(InvoiceAllocation).where(InvoiceAllocation.invoice_id == invoice_id))
    ).scalars().all()
    assert [a.amount for a in allocations] == [Decimal("300")]

    event = (
        await session.execute(
            select(ReconciliationEvent).where(ReconciliationEvent.expectation_id == invoice_id)
        )
    ).scalar_one()
    assert event.action == "accepted"
    assert event.user_id is None
    assert event.detail["auto_applied"] is True
    assert event.detail["threshold"] == 0.9


@pytest.mark.asyncio
async def test_no_bar_means_nothing_happens(
    session: AsyncSession, test_user: User, test_workspace: Workspace, test_account: Account
):
    _, _, suggestion_id = await _setup(session, test_user, test_workspace, test_account)
    result = await auto.auto_apply(session, test_workspace.id, None)
    assert (result.applied, result.skipped) == (0, 0)
    suggestion = await _get(session, ReconciliationSuggestion, suggestion_id)
    assert suggestion.status == "pending"


@pytest.mark.asyncio
async def test_a_low_bar_is_floored_at_half(
    session: AsyncSession, test_user: User, test_workspace: Workspace, test_account: Account
):
    _, _, suggestion_id = await _setup(
        session, test_user, test_workspace, test_account, description=0.4
    )
    result = await auto.auto_apply(session, test_workspace.id, Decimal("0.10"))
    assert result.applied == 0
    suggestion = await _get(session, ReconciliationSuggestion, suggestion_id)
    assert suggestion.status == "pending"


@pytest.mark.asyncio
async def test_one_refusal_does_not_undo_the_others(
    session: AsyncSession, test_user: User, test_workspace: Workspace, test_account: Account
):
    _, _, good_id = await _setup(session, test_user, test_workspace, test_account)
    # A second suggestion whose invoice has since been voided.
    bad_invoice_id, _, bad_id = await _setup(session, test_user, test_workspace, test_account)
    bad_invoice = await _get(session, Invoice, bad_invoice_id)
    bad_invoice.status = "void"
    bad_invoice.number = 2
    await session.commit()
    session.expunge_all()

    result = await auto.auto_apply(session, test_workspace.id, Decimal("0.90"))
    await session.commit()

    assert (result.applied, result.failed) == (1, 1)
    good = await _get(session, ReconciliationSuggestion, good_id)
    bad = await _get(session, ReconciliationSuggestion, bad_id)
    assert good.status == "accepted"
    assert bad.status == "pending"  # left for a person


# ---------------------------------------------------------------------------
# API and the workspace setting
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workspace_setting_is_validated_and_can_be_cleared(
    client: AsyncClient, auth_headers, test_workspace: Workspace
):
    url = f"/api/workspaces/{test_workspace.id}"

    assert (
        await client.patch(url, json={"reconciliation_auto_apply_score": 0.3}, headers=auth_headers)
    ).status_code == 422
    assert (
        await client.patch(url, json={"reconciliation_auto_apply_score": 1.5}, headers=auth_headers)
    ).status_code == 422

    ok = await client.patch(url, json={"reconciliation_auto_apply_score": 0.95}, headers=auth_headers)
    assert ok.status_code == 200
    assert ok.json()["reconciliation_auto_apply_score"] == 0.95

    cleared = await client.patch(url, json={"reconciliation_auto_apply_score": None}, headers=auth_headers)
    assert cleared.json()["reconciliation_auto_apply_score"] is None


@pytest.mark.asyncio
async def test_auto_apply_endpoint_refuses_without_a_bar_and_runs_with_one(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers,
    test_user: User,
    test_workspace: Workspace,
    test_account: Account,
):
    # The matching router belongs to the invoices module, on for business workspaces.
    workspace = await _get(session, Workspace, test_workspace.id)
    workspace.kind = "business"
    await session.commit()
    _, _, suggestion_id = await _setup(session, test_user, test_workspace, test_account)

    refused = await client.post("/api/reconciliation/suggestions/auto-apply", headers=auth_headers)
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "auto_apply_disabled"

    await client.patch(
        f"/api/workspaces/{test_workspace.id}",
        json={"reconciliation_auto_apply_score": 0.9},
        headers=auth_headers,
    )
    ran = await client.post("/api/reconciliation/suggestions/auto-apply", headers=auth_headers)
    assert ran.status_code == 200
    assert ran.json() == {"applied": 1, "skipped": 0, "failed": 0}
    session.expunge_all()
    assert (await _get(session, ReconciliationSuggestion, suggestion_id)).status == "accepted"
