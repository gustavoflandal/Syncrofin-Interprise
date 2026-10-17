"""Tests for invoice withholdings (B3/T6)."""
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio

from app.services.invoice_service import InvoiceError, create_invoice, update_invoice, void_invoice


def _base(total: str, **extra) -> dict:
    return {
        "direction": "receivable",
        "issue_date": date(2026, 10, 1),
        "due_date": date(2026, 11, 1),
        "currency": "BRL",
        "total": Decimal(total),
        **extra,
    }


def _wh(tax_type: str, withheld: str, rate: str | None = None, base: str = "10000.00") -> dict:
    return {
        "tax_type": tax_type,
        "rate": Decimal(rate) if rate else None,
        "base_amount": Decimal(base),
        "withheld_amount": Decimal(withheld),
    }


@pytest.mark.asyncio
async def test_create_invoice_with_withholdings(session, test_workspace, test_user):
    data = _base("10000.00", withholdings=[_wh("irrf", "150.00", "1.5"), _wh("iss", "500.00", "5.0")])
    invoice = await create_invoice(session, test_workspace.id, test_user.id, data)
    await session.commit()
    await session.refresh(invoice, ["withholdings"])

    assert len(invoice.withholdings) == 2
    assert invoice.total_withheld == Decimal("650.00")
    assert invoice.net_receivable == Decimal("9350.00")


@pytest.mark.asyncio
async def test_withholdings_exceed_total_rejected(session, test_workspace, test_user):
    data = _base("1000.00", withholdings=[_wh("irrf", "1500.00", "1.5", "1000.00")])
    with pytest.raises(InvoiceError, match="exceeds invoice total") as exc:
        await create_invoice(session, test_workspace.id, test_user.id, data)
    assert exc.value.code == "withholdings_exceed_total"


@pytest.mark.asyncio
async def test_withholding_on_void_invoice_rejected(session, test_workspace, test_user):
    invoice = await create_invoice(session, test_workspace.id, test_user.id, _base("5000.00"))
    await session.commit()
    assert invoice.status == "open"  # preset de rastreio abre na criação
    await void_invoice(session, invoice)
    await session.commit()

    with pytest.raises(InvoiceError) as exc:
        await update_invoice(
            session, invoice, {"withholdings": [_wh("irrf", "75.00", "1.5", "5000.00")]}
        )
    assert exc.value.code == "terminal_status"


@pytest.mark.asyncio
async def test_duplicate_withholding_type_rejected(session, test_workspace, test_user):
    data = _base("10000.00", withholdings=[_wh("irrf", "150.00"), _wh("irrf", "200.00")])
    with pytest.raises(InvoiceError) as exc:
        await create_invoice(session, test_workspace.id, test_user.id, data)
    assert exc.value.code == "duplicate_withholding_type"


@pytest.mark.asyncio
async def test_update_replaces_withholdings(session, test_workspace, test_user):
    data = _base("10000.00", withholdings=[_wh("irrf", "150.00")])
    invoice = await create_invoice(session, test_workspace.id, test_user.id, data)
    await update_invoice(session, invoice, {"withholdings": [_wh("iss", "500.00")]})
    assert [w.tax_type for w in invoice.withholdings] == ["iss"]


# --- API -------------------------------------------------------------------
@pytest_asyncio.fixture
async def biz_headers(client, auth_headers) -> dict:
    resp = await client.post(
        "/api/workspaces",
        headers=auth_headers,
        json={"name": "Studio", "kind": "business", "self_membership": True},
    )
    assert resp.status_code == 201, resp.text
    return {**auth_headers, "X-Workspace-Id": resp.json()["id"]}


async def _api_invoice(client, headers, **extra) -> dict:
    payload = {
        "total": "10000.00",
        "due_date": "2026-11-01",
        "lines": [{"description": "Servico", "quantity": "1", "unit_price": "10000.00"}],
        "as_draft": True,
        **extra,
    }
    resp = await client.post("/api/invoices", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


_IRRF = {"tax_type": "irrf", "rate": "1.5", "base_amount": "10000.00", "withheld_amount": "150.00"}


@pytest.mark.asyncio
async def test_add_withholding_via_api(client, biz_headers):
    inv = await _api_invoice(client, biz_headers)
    resp = await client.post(f"/api/invoices/{inv['id']}/withholdings", json=_IRRF, headers=biz_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tax_type"] == "irrf"
    assert Decimal(body["withheld_amount"]) == Decimal("150.00")


@pytest.mark.asyncio
async def test_add_duplicate_and_excess_withholding_rejected(client, biz_headers):
    inv = await _api_invoice(client, biz_headers)
    url = f"/api/invoices/{inv['id']}/withholdings"
    assert (await client.post(url, json=_IRRF, headers=biz_headers)).status_code == 201
    dup = await client.post(url, json=_IRRF, headers=biz_headers)
    assert dup.status_code == 422
    assert dup.json()["detail"]["code"] == "duplicate_withholding_type"
    big = await client.post(
        url, json={**_IRRF, "tax_type": "iss", "withheld_amount": "9900.00"}, headers=biz_headers
    )
    assert big.status_code == 422
    assert big.json()["detail"]["code"] == "withholdings_exceed_total"


@pytest.mark.asyncio
async def test_update_withholding_via_api(client, biz_headers):
    inv = await _api_invoice(client, biz_headers)
    url = f"/api/invoices/{inv['id']}/withholdings"
    wid = (await client.post(url, json=_IRRF, headers=biz_headers)).json()["id"]
    resp = await client.patch(f"{url}/{wid}", json={"withheld_amount": "200.00"}, headers=biz_headers)
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()["withheld_amount"]) == Decimal("200.00")
    assert resp.json()["tax_type"] == "irrf"


@pytest.mark.asyncio
async def test_delete_withholding_via_api(client, biz_headers):
    inv = await _api_invoice(client, biz_headers)
    url = f"/api/invoices/{inv['id']}/withholdings"
    wid = (await client.post(url, json=_IRRF, headers=biz_headers)).json()["id"]
    assert (await client.delete(f"{url}/{wid}", headers=biz_headers)).status_code == 204
    assert (await client.delete(f"{url}/{wid}", headers=biz_headers)).status_code == 404
