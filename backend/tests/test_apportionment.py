"""Rateio de transações entre centros de custo (A8)."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cost_center import CostCenter
from app.models.transaction import Transaction


@pytest_asyncio.fixture
async def centers(session: AsyncSession, test_workspace) -> list[CostCenter]:
    rows = [CostCenter(workspace_id=test_workspace.id, name=n) for n in ("Vendas", "TI", "RH")]
    session.add_all(rows)
    await session.commit()
    return rows


@pytest_asyncio.fixture
async def tx(session: AsyncSession, test_user, test_workspace, test_account) -> Transaction:
    row = Transaction(
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        account_id=test_account.id,
        description="Aluguel",
        amount=Decimal("100.00"),
        currency="BRL",
        date=date(2026, 3, 10),
        type="debit",
        source="manual",
    )
    session.add(row)
    await session.commit()
    return row


def _url(tx: Transaction) -> str:
    return f"/api/transactions/{tx.id}/allocations"


@pytest.mark.asyncio
async def test_set_by_percentage_puts_residual_on_last(client: AsyncClient, auth_headers, tx, centers):
    body = [{"cost_center_id": str(c.id), "percentage": "33.3333"} for c in centers]
    r = await client.put(_url(tx), json=body, headers=auth_headers)
    assert r.status_code == 200, r.text
    amounts = [Decimal(a["amount"]) for a in r.json()]
    assert amounts == [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")]
    assert sum(amounts) == Decimal("100.00")


@pytest.mark.asyncio
async def test_set_by_amount_exact_sum_and_read_back(client: AsyncClient, auth_headers, tx, centers):
    body = [
        {"cost_center_id": str(centers[0].id), "amount": "70.00"},
        {"cost_center_id": str(centers[1].id), "amount": "30.00"},
    ]
    r = await client.put(_url(tx), json=body, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert [Decimal(a["percentage"]) for a in r.json()] == [Decimal("70"), Decimal("30")]
    assert r.json()[0]["cost_center_name"] == "Vendas"

    listed = await client.get(_url(tx), headers=auth_headers)
    assert len(listed.json()) == 2
    # a transação expõe o rateio e aponta para o centro de maior fatia
    detail = await client.get(f"/api/transactions/{tx.id}", headers=auth_headers)
    assert len(detail.json()["cost_center_allocations"]) == 2
    assert detail.json()["cost_center_id"] == str(centers[0].id)


@pytest.mark.asyncio
async def test_percentage_not_100_is_rejected(client: AsyncClient, auth_headers, tx, centers):
    body = [
        {"cost_center_id": str(centers[0].id), "percentage": "60"},
        {"cost_center_id": str(centers[1].id), "percentage": "30"},
    ]
    r = await client.put(_url(tx), json=body, headers=auth_headers)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "allocations_percentage_sum"


@pytest.mark.asyncio
async def test_amount_not_matching_transaction_is_rejected(client: AsyncClient, auth_headers, tx, centers):
    body = [
        {"cost_center_id": str(centers[0].id), "amount": "60.00"},
        {"cost_center_id": str(centers[1].id), "amount": "30.00"},
    ]
    r = await client.put(_url(tx), json=body, headers=auth_headers)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "allocations_amount_sum"


@pytest.mark.asyncio
async def test_foreign_cost_center_is_rejected(client: AsyncClient, auth_headers, tx, centers):
    body = [{"cost_center_id": str(uuid.uuid4()), "percentage": "100"}]
    r = await client.put(_url(tx), json=body, headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_clear_allocations(client: AsyncClient, auth_headers, tx, centers):
    body = [{"cost_center_id": str(c.id), "percentage": p} for c, p in zip(centers[:2], ("50", "50"))]
    assert (await client.put(_url(tx), json=body, headers=auth_headers)).status_code == 200
    assert (await client.delete(_url(tx), headers=auth_headers)).status_code == 204
    assert (await client.get(_url(tx), headers=auth_headers)).json() == []


@pytest.mark.asyncio
async def test_closed_period_blocks_allocation(client: AsyncClient, auth_headers, test_workspace, tx, centers):
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/period-closes",
        json={"year": 2026, "month": 3},
        headers=auth_headers,
    )
    assert r.status_code == 201
    body = [{"cost_center_id": str(centers[0].id), "percentage": "100"}]
    r = await client.put(_url(tx), json=body, headers=auth_headers)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "period_closed"


@pytest.mark.asyncio
async def test_dre_by_cost_center_uses_the_slice(client: AsyncClient, auth_headers, tx, centers):
    body = [
        {"cost_center_id": str(centers[0].id), "amount": "70.00"},
        {"cost_center_id": str(centers[1].id), "amount": "30.00"},
    ]
    await client.put(_url(tx), json=body, headers=auth_headers)

    def total(report: dict) -> Decimal:
        return sum((Decimal(str(s["subtotal"])) for s in report["sections"]), Decimal("0"))

    totals = []
    for c in centers:
        r = await client.get(
            f"/api/reports/dre?year=2026&month=3&cost_center_id={c.id}", headers=auth_headers
        )
        assert r.status_code == 200, r.text
        totals.append(total(r.json()))
    assert totals == [Decimal("70.00"), Decimal("30.00"), Decimal("0")]


@pytest.mark.asyncio
async def test_editing_amount_rescales_slices(client: AsyncClient, auth_headers, tx, centers):
    body = [
        {"cost_center_id": str(centers[0].id), "amount": "75.00"},
        {"cost_center_id": str(centers[1].id), "amount": "25.00"},
    ]
    await client.put(_url(tx), json=body, headers=auth_headers)
    r = await client.patch(f"/api/transactions/{tx.id}", json={"amount": "200.00"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    amounts = [Decimal(a["amount"]) for a in (await client.get(_url(tx), headers=auth_headers)).json()]
    assert amounts == [Decimal("150.00"), Decimal("50.00")]
