"""In-app notifications: what triggers them, that they are told once, who sees them."""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.bank_connection import BankConnection
from app.models.budget import Budget
from app.models.category import Category
from app.models.invoice import Invoice
from app.models.notification import Notification
from app.models.transaction import Transaction
from app.models.user import User
from app.models.workspace import Workspace
from app.services import notification_delivery as delivery
from app.services import notification_service as ns


def test_money_formats_brazilian_reais():
    assert ns._money(Decimal("1234.5")) == "R$ 1.234,50"
    assert ns._money(Decimal("0.5")) == "R$ 0,50"
    assert ns._money(Decimal("1234.5"), "USD") == "1,234.50 USD"


async def _count(session: AsyncSession, user: User) -> int:
    return (
        await session.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id))
    ) or 0


async def _spend(session, user, account, category, amount):
    session.add(
        Transaction(
            id=uuid.uuid4(),
            user_id=user.id,
            account_id=account.id,
            category_id=category.id,
            description="gasto",
            amount=Decimal(amount),
            currency="BRL",
            date=date.today(),
            type="debit",
            source="manual",
            created_at=datetime.now(timezone.utc),
        )
    )


def _budget(user, category, amount) -> Budget:
    return Budget(
        id=uuid.uuid4(),
        user_id=user.id,
        category_id=category.id,
        amount=Decimal(amount),
        month=date.today().replace(day=1),
        currency="BRL",
    )


@pytest.mark.asyncio
async def test_budget_over_notifies_once_however_often_it_runs(
    session: AsyncSession,
    test_user: User,
    test_workspace: Workspace,
    test_account: Account,
    test_categories: list[Category],
):
    food = test_categories[0]
    session.add(_budget(test_user, food, "100"))
    await _spend(session, test_user, test_account, food, "130")
    await session.commit()

    first = await ns.generate_for_workspace(session, test_workspace)
    await session.commit()
    second = await ns.generate_for_workspace(session, test_workspace)
    await session.commit()

    assert [n.kind for n in first] == ["budget_over"]
    assert first[0].severity == "critical"
    assert "Alimentação" in first[0].title
    assert "R$ 130,00" in first[0].body
    assert second == []
    assert await _count(session, test_user) == 1


@pytest.mark.asyncio
async def test_budget_near_the_limit_is_a_warning_not_an_alarm(
    session: AsyncSession,
    test_user: User,
    test_workspace: Workspace,
    test_account: Account,
    test_categories: list[Category],
):
    food = test_categories[0]
    session.add(_budget(test_user, food, "100"))
    await _spend(session, test_user, test_account, food, "85")
    await session.commit()

    created = await ns.generate_for_workspace(session, test_workspace)
    assert [(n.kind, n.severity) for n in created] == [("budget_warning", "warning")]


@pytest.mark.asyncio
async def test_a_budget_within_limits_says_nothing(
    session: AsyncSession,
    test_user: User,
    test_workspace: Workspace,
    test_account: Account,
    test_categories: list[Category],
):
    food = test_categories[0]
    session.add(_budget(test_user, food, "100"))
    await _spend(session, test_user, test_account, food, "20")
    await session.commit()

    assert await ns.generate_for_workspace(session, test_workspace) == []


def _invoice(user, workspace, *, due, direction="receivable", number=1) -> Invoice:
    return Invoice(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        direction=direction,
        status="open",
        number=number,
        currency="BRL",
        subtotal=Decimal("300"),
        total=Decimal("300"),
        issue_date=date.today() - timedelta(days=30),
        due_date=due,
    )


@pytest.mark.asyncio
async def test_invoice_due_soon_and_overdue(
    session: AsyncSession, test_user: User, test_workspace: Workspace
):
    today = date.today()
    session.add(_invoice(test_user, test_workspace, due=today + timedelta(days=2), number=1))
    session.add(_invoice(test_user, test_workspace, due=today - timedelta(days=9), number=2))
    session.add(_invoice(test_user, test_workspace, due=today + timedelta(days=30), number=3))
    await session.commit()

    created = await ns.generate_for_workspace(session, test_workspace)
    kinds = sorted(n.kind for n in created)

    assert kinds == ["invoice_due", "invoice_overdue"]  # the one due in 30 days is quiet
    overdue = next(n for n in created if n.kind == "invoice_overdue")
    assert overdue.severity == "critical"  # money owed to us
    assert "9 dia" in overdue.title


@pytest.mark.asyncio
async def test_an_overdue_payable_is_a_warning(
    session: AsyncSession, test_user: User, test_workspace: Workspace
):
    session.add(
        _invoice(test_user, test_workspace, due=date.today() - timedelta(days=1),
                 direction="payable", number=4)
    )
    await session.commit()
    created = await ns.generate_for_workspace(session, test_workspace)
    assert created[0].severity == "warning"
    assert created[0].title.startswith("Conta a pagar")


@pytest.mark.asyncio
async def test_a_paid_invoice_is_not_chased(
    session: AsyncSession, test_user: User, test_workspace: Workspace
):
    invoice = _invoice(test_user, test_workspace, due=date.today() - timedelta(days=5), number=5)
    invoice.total = Decimal("0")
    invoice.subtotal = Decimal("0")
    session.add(invoice)
    await session.commit()
    assert await ns.generate_for_workspace(session, test_workspace) == []


@pytest.mark.asyncio
async def test_failed_bank_sync_notifies_the_connection_owner(
    session: AsyncSession,
    test_user: User,
    test_workspace: Workspace,
    test_connection: BankConnection,
):
    test_connection.status = "expired"
    await session.commit()

    created = await ns.generate_for_workspace(session, test_workspace)

    assert [n.kind for n in created] == ["sync_failed"]
    assert created[0].user_id == test_user.id
    assert "Banco Teste" in created[0].title
    assert created[0].title.startswith("Reconecte")


@pytest.mark.asyncio
async def test_negative_forecast_notifies_once_a_week(
    session: AsyncSession, test_user: User, test_workspace: Workspace, test_account: Account
):
    test_account.balance = Decimal("100")
    test_account.currency = "BRL"
    session.add(
        _invoice(test_user, test_workspace, due=date.today() + timedelta(days=5),
                 direction="payable", number=6)
    )
    await session.commit()

    first = await ns.generate_for_workspace(session, test_workspace)
    await session.commit()
    again = await ns.generate_for_workspace(session, test_workspace)

    assert "cashflow_negative" in [n.kind for n in first]
    assert again == []


@pytest.mark.asyncio
async def test_viewers_are_not_notified(
    session: AsyncSession, test_workspace: Workspace, viewer_auth_headers, test_user: User
):
    recipients = await ns.recipients(session, test_workspace.id)
    assert test_user.id in recipients
    assert len(recipients) == 1  # the viewer fixture's user is not among them


@pytest.mark.asyncio
async def test_a_failing_generator_does_not_silence_the_others(
    session: AsyncSession,
    test_user: User,
    test_workspace: Workspace,
    monkeypatch,
):
    async def boom(*args, **kwargs):
        raise RuntimeError("forecast is down")

    monkeypatch.setattr(ns, "forecast_drafts", boom)
    session.add(_invoice(test_user, test_workspace, due=date.today(), number=8))
    await session.commit()

    created = await ns.generate_for_workspace(session, test_workspace)
    assert [n.kind for n in created] == ["invoice_due"]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_requires_authentication(client: AsyncClient):
    assert (await client.get("/api/notifications")).status_code == 401


@pytest.mark.asyncio
async def test_inbox_flow(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers,
    test_user: User,
    test_workspace: Workspace,
):
    session.add(_invoice(test_user, test_workspace, due=date.today() + timedelta(days=1), number=9))
    session.add(_invoice(test_user, test_workspace, due=date.today() - timedelta(days=2), number=10))
    await session.commit()

    refreshed = await client.post("/api/notifications/refresh", headers=auth_headers)
    assert refreshed.json() == {"unread": 2}
    # pressing the button again changes nothing
    assert (await client.post("/api/notifications/refresh", headers=auth_headers)).json() == {"unread": 2}

    listing = (await client.get("/api/notifications", headers=auth_headers)).json()
    assert len(listing) == 2 and all(n["read_at"] is None for n in listing)

    one = listing[0]["id"]
    assert (await client.post(f"/api/notifications/{one}/read", headers=auth_headers)).status_code == 204
    assert (await client.get("/api/notifications/unread-count", headers=auth_headers)).json() == {"unread": 1}
    # reading twice is a 404: there was nothing left to do
    assert (await client.post(f"/api/notifications/{one}/read", headers=auth_headers)).status_code == 404

    unread = (await client.get("/api/notifications", params={"unread_only": True}, headers=auth_headers)).json()
    assert len(unread) == 1

    assert (await client.post("/api/notifications/read-all", headers=auth_headers)).json() == {"unread": 0}


@pytest.mark.asyncio
async def test_you_cannot_read_someone_elses_notification(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers,
    viewer_auth_headers,
    test_user: User,
    test_workspace: Workspace,
):
    session.add(_invoice(test_user, test_workspace, due=date.today(), number=11))
    await session.commit()
    await client.post("/api/notifications/refresh", headers=auth_headers)
    mine = (await client.get("/api/notifications", headers=auth_headers)).json()[0]["id"]

    # the viewer neither sees it nor can mark it read
    assert (await client.get("/api/notifications", headers=viewer_auth_headers)).json() == []
    assert (
        await client.post(f"/api/notifications/{mine}/read", headers=viewer_auth_headers)
    ).status_code == 404
    assert (await client.get("/api/notifications/unread-count", headers=auth_headers)).json() == {"unread": 1}


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------
def test_webhook_signature_is_a_stable_hmac():
    assert delivery.sign("s3cret", b"{}") == delivery.sign("s3cret", b"{}")
    assert delivery.sign("s3cret", b"{}") != delivery.sign("other", b"{}")
    assert delivery.sign("s3cret", b"{}").startswith("sha256=")


def _notification(user: User, workspace: Workspace) -> Notification:
    return Notification(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        user_id=user.id,
        kind="budget_over",
        severity="critical",
        title="Orçamento estourado: Alimentação",
        body="corpo",
        data={"route": "/budgets"},
        dedupe_key="k",
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_delivery_is_a_no_op_when_no_channel_is_configured(
    session: AsyncSession, test_user: User, test_workspace: Workspace
):
    note = _notification(test_user, test_workspace)
    assert await delivery.deliver(session, [note]) == 0
    assert note.delivered_at is None


def test_email_carries_the_deep_link():
    from app.core.config import Settings

    settings = Settings(smtp_host="smtp.example", smtp_from="SyncroFin <a@b.co>", frontend_url="https://x.io/")
    note = Notification(
        id=uuid.uuid4(), workspace_id=uuid.uuid4(), user_id=uuid.uuid4(), kind="k", severity="info",
        title="T", body="B", data={"route": "/budgets"}, dedupe_key="k",
    )
    msg = delivery.build_message(settings, "dest@x.io", note)
    assert msg["Subject"] == "[SyncroFin] T"
    assert "https://x.io/budgets" in msg.get_content()


@pytest.mark.asyncio
async def test_webhook_failure_does_not_raise_and_is_not_retried(
    session: AsyncSession, test_user: User, test_workspace: Workspace, monkeypatch
):
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "notifications_webhook_url", "http://127.0.0.1:9/hook")

    async def refuse(*args, **kwargs):
        raise ConnectionError("nope")

    monkeypatch.setattr(delivery, "_post_webhook", refuse)
    note = _notification(test_user, test_workspace)

    handed = await delivery.deliver(session, [note])

    assert handed == 0  # nothing got through...
    assert note.delivered_at is not None  # ...and we still will not try again
