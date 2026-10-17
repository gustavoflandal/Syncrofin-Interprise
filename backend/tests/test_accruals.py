"""Provisões e diferimentos (A8)."""
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction
from app.services import accrual_service


def _payload(account, **over) -> dict:
    body = {
        "type": "accrual",
        "description": "Provisão de férias",
        "total_amount": "1000.00",
        "start_date": "2026-01-15",
        "end_date": "2026-03-20",
        "account_id": str(account.id),
    }
    body.update(over)
    return body


@pytest.mark.asyncio
async def test_create_schedule_generates_monthly_entries(client: AsyncClient, auth_headers, test_account):
    r = await client.post("/api/accruals", json=_payload(test_account), headers=auth_headers)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["period_count"] == 3
    assert [e["period_date"] for e in data["entries"]] == ["2026-01-01", "2026-02-01", "2026-03-01"]
    assert {e["status"] for e in data["entries"]} == {"pending"}
    assert data["pending_count"] == 3 and data["posted_count"] == 0


@pytest.mark.asyncio
async def test_amount_distribution_puts_residual_on_last(client: AsyncClient, auth_headers, test_account):
    r = await client.post("/api/accruals", json=_payload(test_account), headers=auth_headers)
    amounts = [Decimal(e["amount"]) for e in r.json()["entries"]]
    assert amounts == [Decimal("333.33"), Decimal("333.33"), Decimal("333.34")]
    assert sum(amounts) == Decimal("1000.00")
    assert Decimal(r.json()["amount_per_period"]) == Decimal("333.33")


def test_distribute_helper_sums_exactly():
    parts = accrual_service.distribute(Decimal("100.00"), 7)
    assert sum(parts) == Decimal("100.00") and len(parts) == 7


@pytest.mark.asyncio
async def test_invalid_range_is_rejected(client: AsyncClient, auth_headers, test_account):
    r = await client.post(
        "/api/accruals",
        json=_payload(test_account, start_date="2026-05-01", end_date="2026-05-01"),
        headers=auth_headers,
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "accrual_invalid_range"


@pytest.mark.asyncio
async def test_post_entries_creates_transactions(
    client: AsyncClient, auth_headers, session: AsyncSession, test_account
):
    created = (await client.post("/api/accruals", json=_payload(test_account), headers=auth_headers)).json()
    r = await client.post("/api/accruals/post", json={"up_to_date": "2026-02-28"}, headers=auth_headers)
    assert r.status_code == 200 and r.json() == {"posted": 2, "skipped": 0}

    detail = (await client.get(f"/api/accruals/{created['id']}", headers=auth_headers)).json()
    assert [e["status"] for e in detail["entries"]] == ["posted", "posted", "pending"]
    txs = (await session.execute(select(Transaction).where(Transaction.source == "accrual"))).scalars().all()
    assert len(txs) == 2 and {t.type for t in txs} == {"debit"}

    # idempotente: repetir não duplica
    again = await client.post("/api/accruals/post", json={"up_to_date": "2026-02-28"}, headers=auth_headers)
    assert again.json() == {"posted": 0, "skipped": 0}


@pytest.mark.asyncio
async def test_deferral_posts_credits(client: AsyncClient, auth_headers, session: AsyncSession, test_account):
    await client.post("/api/accruals", json=_payload(test_account, type="deferral"), headers=auth_headers)
    await client.post("/api/accruals/post", json={"up_to_date": "2026-01-31"}, headers=auth_headers)
    tx = (await session.execute(select(Transaction).where(Transaction.source == "accrual"))).scalar_one()
    assert tx.type == "credit" and tx.date == date(2026, 1, 1)


@pytest.mark.asyncio
async def test_closed_period_entry_is_skipped(
    client: AsyncClient, auth_headers, test_workspace, test_account
):
    created = (await client.post("/api/accruals", json=_payload(test_account), headers=auth_headers)).json()
    await client.post(
        f"/api/workspaces/{test_workspace.id}/period-closes",
        json={"year": 2026, "month": 1},
        headers=auth_headers,
    )
    r = await client.post("/api/accruals/post", json={"up_to_date": "2026-02-28"}, headers=auth_headers)
    assert r.json() == {"posted": 1, "skipped": 1}
    detail = (await client.get(f"/api/accruals/{created['id']}", headers=auth_headers)).json()
    assert [e["status"] for e in detail["entries"]] == ["skipped", "posted", "pending"]
    assert detail["skipped_count"] == 1


@pytest.mark.asyncio
async def test_cancel_schedule_stops_further_posting(
    client: AsyncClient, auth_headers, session: AsyncSession, test_account
):
    created = (await client.post("/api/accruals", json=_payload(test_account), headers=auth_headers)).json()
    await client.post("/api/accruals/post", json={"up_to_date": "2026-01-31"}, headers=auth_headers)
    r = await client.delete(f"/api/accruals/{created['id']}", headers=auth_headers)
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert r.json()["posted_count"] == 1  # o já lançado permanece

    after = await client.post("/api/accruals/post", json={"up_to_date": "2026-12-31"}, headers=auth_headers)
    assert after.json() == {"posted": 0, "skipped": 0}
    txs = (await session.execute(select(Transaction).where(Transaction.source == "accrual"))).scalars().all()
    assert len(txs) == 1


@pytest.mark.asyncio
async def test_list_schedules(client: AsyncClient, auth_headers, test_account):
    await client.post("/api/accruals", json=_payload(test_account), headers=auth_headers)
    r = await client.get("/api/accruals", headers=auth_headers)
    assert r.status_code == 200 and len(r.json()) == 1
    assert r.json()[0]["pending_count"] == 3
