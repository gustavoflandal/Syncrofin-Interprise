"""Integration tests for AP/AR overview, title list, forecast, DRE endpoints and NF-e import.

Covers:
- Authentication gate on /api/ar-ap/overview (401 without token)
- Owner can read the AP/AR overview and receives the expected fields
- GET /api/ar-ap/titles returns paginated list with expected fields
- GET /api/ar-ap/forecast returns bucket structure
- DRE endpoint returns the expected schema fields
- DRE XLSX export returns an application/spreadsheetml response
- POST /api/ar-ap/import/nfe imports XML files as payable invoices
"""
import pytest
from httpx import AsyncClient

from app.models.workspace import Workspace

_NF_NS = "http://www.portalfiscal.inf.br/nfe"
_CHAVE_A = "35200607677851000107550010000037021988210001"
_CHAVE_B = "35200607677851000107550010000037021988210002"


def _nfe_xml(chave: str = _CHAVE_A, total: str = "500.00") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<NFe xmlns="{_NF_NS}">
  <infNFe Id="NFe{chave}" versao="4.00">
    <ide>
      <nNF>3702</nNF>
      <serie>1</serie>
      <dhEmi>2020-06-12T10:30:00-03:00</dhEmi>
    </ide>
    <emit>
      <CNPJ>07677851000107</CNPJ>
      <xNome>FORNECEDOR TESTE LTDA</xNome>
    </emit>
    <total>
      <ICMSTot>
        <vProd>{total}</vProd>
        <vDesc>0.00</vDesc>
        <vNF>{total}</vNF>
      </ICMSTot>
    </total>
    <cobr>
      <dup>
        <nDup>001</nDup>
        <dVenc>2020-07-12</dVenc>
        <vDup>{total}</vDup>
      </dup>
    </cobr>
  </infNFe>
</NFe>""".encode("utf-8")

pytestmark = pytest.mark.asyncio


async def test_overview_unauthenticated(client: AsyncClient):
    """Requesting the AP/AR overview without a token must return 401."""
    response = await client.get("/api/ar-ap/overview")
    assert response.status_code == 401


async def test_overview_owner_ok(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
):
    """The workspace owner can read the AP/AR overview and receives the
    expected top-level fields even when there are no invoices yet."""
    headers = {**auth_headers, "X-Workspace-Id": str(test_workspace.id)}
    response = await client.get("/api/ar-ap/overview", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert "receivable" in data, f"missing 'receivable' key: {list(data.keys())}"
    assert "payable" in data, f"missing 'payable' key: {list(data.keys())}"
    assert "net_position" in data, f"missing 'net_position' key: {list(data.keys())}"
    # With no invoices the outstanding amounts must be zero on both sides.
    assert data["receivable"]["outstanding"] == "0.00"
    assert data["payable"]["outstanding"] == "0.00"


async def test_titles_endpoint_empty(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
):
    """GET /api/ar-ap/titles returns an empty page when there are no invoices."""
    headers = {**auth_headers, "X-Workspace-Id": str(test_workspace.id)}
    resp = await client.get("/api/ar-ap/titles?direction=receivable", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert data["items"] == []
    assert data["total"] == 0


async def test_titles_endpoint_unauthenticated(client: AsyncClient):
    """Requesting the titles list without a token must return 401."""
    resp = await client.get("/api/ar-ap/titles")
    assert resp.status_code == 401


async def test_titles_payable_direction(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
):
    """direction=payable is accepted and returns an empty page."""
    headers = {**auth_headers, "X-Workspace-Id": str(test_workspace.id)}
    resp = await client.get("/api/ar-ap/titles?direction=payable", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []


async def test_forecast_endpoint(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
):
    """GET /api/ar-ap/forecast returns a buckets list with the expected fields."""
    headers = {**auth_headers, "X-Workspace-Id": str(test_workspace.id)}
    resp = await client.get(
        "/api/ar-ap/forecast?currency=BRL&period=month&num_buckets=3",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["currency"] == "BRL"
    assert data["period"] == "month"
    assert len(data["buckets"]) == 3
    first = data["buckets"][0]
    assert "label" in first
    assert "receivable" in first
    assert "payable" in first
    assert "net" in first


async def test_forecast_week_period(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
):
    """period=week returns ISO week labels."""
    headers = {**auth_headers, "X-Workspace-Id": str(test_workspace.id)}
    resp = await client.get(
        "/api/ar-ap/forecast?currency=BRL&period=week&num_buckets=4",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["period"] == "week"
    assert len(data["buckets"]) == 4
    # ISO week label looks like "2026-W41"
    assert "W" in data["buckets"][0]["label"]


async def test_dre_endpoint(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
):
    """GET /api/reports/dre returns 200 and the expected schema fields."""
    headers = {**auth_headers, "X-Workspace-Id": str(test_workspace.id)}
    response = await client.get(
        "/api/reports/dre?year=2026&month=1", headers=headers
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "gross_revenue" in data, f"missing 'gross_revenue': {list(data.keys())}"
    assert "result" in data, f"missing 'result': {list(data.keys())}"


async def test_dre_export_xlsx(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
):
    """GET /api/reports/dre/export with format=xlsx returns a spreadsheet."""
    headers = {**auth_headers, "X-Workspace-Id": str(test_workspace.id)}
    response = await client.get(
        "/api/reports/dre/export?year=2026&month=1&format=xlsx",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    content_type = response.headers.get("content-type", "")
    assert "spreadsheetml" in content_type, (
        f"Expected a spreadsheetml content-type, got: {content_type!r}"
    )


# ── NF-e XML import ───────────────────────────────────────────────────────────


async def test_import_nfe_unauthenticated(client: AsyncClient):
    """POST /api/ar-ap/import/nfe sem token deve retornar 401."""
    resp = await client.post(
        "/api/ar-ap/import/nfe",
        files=[("files", ("nota.xml", _nfe_xml(), "text/xml"))],
    )
    assert resp.status_code == 401


async def test_import_nfe_single_file(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
):
    """Um XML válido cria um título a pagar com status='imported'."""
    headers = {**auth_headers, "X-Workspace-Id": str(test_workspace.id)}
    resp = await client.post(
        "/api/ar-ap/import/nfe",
        files=[("files", ("nota.xml", _nfe_xml(), "text/xml"))],
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["imported"] == 1
    assert data["duplicates"] == 0
    assert data["errors"] == 0
    row = data["rows"][0]
    assert row["status"] == "imported"
    assert row["chave"] == _CHAVE_A
    assert row["supplier_name"] == "FORNECEDOR TESTE LTDA"
    assert row["invoice_id"] is not None


async def test_import_nfe_duplicate(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
):
    """A mesma chave importada duas vezes retorna duplicate na segunda chamada."""
    headers = {**auth_headers, "X-Workspace-Id": str(test_workspace.id)}
    xml = _nfe_xml(_CHAVE_B)
    # First import
    r1 = await client.post(
        "/api/ar-ap/import/nfe",
        files=[("files", ("nota.xml", xml, "text/xml"))],
        headers=headers,
    )
    assert r1.status_code == 200
    assert r1.json()["imported"] == 1
    # Second import of same file
    r2 = await client.post(
        "/api/ar-ap/import/nfe",
        files=[("files", ("nota.xml", xml, "text/xml"))],
        headers=headers,
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["imported"] == 0
    assert data["duplicates"] == 1
    assert data["rows"][0]["status"] == "duplicate"


async def test_import_nfe_invalid_xml(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
):
    """XML inválido retorna status='error' sem abortar (não 422)."""
    headers = {**auth_headers, "X-Workspace-Id": str(test_workspace.id)}
    resp = await client.post(
        "/api/ar-ap/import/nfe",
        files=[("files", ("bad.xml", b"not xml", "text/xml"))],
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["errors"] == 1
    assert data["rows"][0]["status"] == "error"


async def test_import_nfe_multiple_files(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace: Workspace,
):
    """Dois XMLs distintos são importados de uma vez."""
    headers = {**auth_headers, "X-Workspace-Id": str(test_workspace.id)}
    xml_a = _nfe_xml("35200607677851000107550010000037021988210003")
    xml_b = _nfe_xml("35200607677851000107550010000037021988210004")
    resp = await client.post(
        "/api/ar-ap/import/nfe",
        files=[
            ("files", ("nota_a.xml", xml_a, "text/xml")),
            ("files", ("nota_b.xml", xml_b, "text/xml")),
        ],
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["imported"] == 2
    assert data["errors"] == 0
