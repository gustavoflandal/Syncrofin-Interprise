"""Conectores ERP (F3): CRUD, adaptador Omie com HTTP simulado, mapeamento e execuções."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.erp import ErpError, available_connectors, get_connector
from app.erp.base import (
    ErpAccount,
    ErpConnector,
    ErpInvoice,
    ErpPayee,
    SyncResult,
)
from app.erp.contaazul import ContaAzulConnector
from app.erp.omie import OmieConnector, integration_code
from app.models.category import Category
from app.models.erp_connection import ErpEntityMapping
from app.models.invoice import Invoice
from app.models.payee import Payee, PayeeTaxId
from app.models.workspace import Workspace
from app.services import erp_service

CREDS = {"app_key": "KEY123", "app_secret": "SECRET456"}


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _omie(handler, **kw) -> OmieConnector:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OmieConnector(client=client, min_interval=0, **CREDS, **kw)


class FakeConnector:
    name = "omie"

    def __init__(self, accounts=None, payees=None, invoice_result=None):
        self.accounts = accounts or []
        self.payees = payees or []
        self.invoice_result = invoice_result
        self.pushed_invoices: list[ErpInvoice] = []
        self.last_message = None

    async def test_connection(self):
        return True

    async def pull_chart_of_accounts(self):
        return self.accounts

    async def pull_payees(self):
        return self.payees

    async def push_transactions(self, transactions):
        return SyncResult(skipped=len(transactions))

    async def push_invoices(self, invoices):
        self.pushed_invoices = list(invoices)
        if self.invoice_result is not None:
            return self.invoice_result
        return SyncResult(
            created=len(invoices), synced_external_ids=[i.external_id for i in invoices]
        )


@pytest.fixture
def fake_connector():
    fake = FakeConnector()
    with patch.object(erp_service, "build_connector", lambda conn: fake):
        yield fake


async def _connection(session: AsyncSession, ws: Workspace, user_id: uuid.UUID):
    conn = await erp_service.create_connection(
        session, ws.id, "omie", dict(CREDS), {"default_category_code": "1.01"}, user_id
    )
    await session.flush()
    return conn


# ────────────────────────────────────────────────────────────────────────────
# Registro e contrato
# ────────────────────────────────────────────────────────────────────────────

def test_registry_lists_builtin_connectors():
    assert {"omie", "contaazul"} <= set(available_connectors())
    assert isinstance(get_connector("omie", **CREDS), ErpConnector)
    with pytest.raises(ValueError):
        get_connector("nao-existe")


@pytest.mark.asyncio
async def test_contaazul_is_a_stub():
    c = ContaAzulConnector()
    assert await c.test_connection() is False
    assert "coming soon" in c.last_message
    with pytest.raises(NotImplementedError):
        await c.pull_payees()
    with pytest.raises(NotImplementedError):
        await c.push_invoices([])


# ────────────────────────────────────────────────────────────────────────────
# Adaptador Omie (HTTP simulado)
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_omie_test_connection_sends_credentials_and_method():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"empresas_cadastro": []})

    assert await _omie(handler).test_connection() is True
    assert seen["url"] == "https://app.omie.com.br/api/v1/geral/empresas/"
    assert seen["body"]["call"] == "ListarEmpresas"
    assert seen["body"]["app_key"] == "KEY123" and seen["body"]["app_secret"] == "SECRET456"
    assert isinstance(seen["body"]["param"], list)


@pytest.mark.asyncio
async def test_omie_test_connection_false_on_fault():
    def handler(request):
        return httpx.Response(
            500, json={"faultstring": "ERROR: App Key ou App Secret inválidos", "faultcode": "X"}
        )

    c = _omie(handler)
    assert await c.test_connection() is False
    assert "inválidos" in c.last_message


@pytest.mark.asyncio
async def test_omie_pull_payees_paginates_and_classifies_documents():
    import json

    def handler(request):
        page = json.loads(request.content)["param"][0]["pagina"]
        rows = {
            1: [
                {"codigo_cliente_omie": 11, "razao_social": "ACME LTDA", "cnpj_cpf": "11.222.333/0001-81"},
                {"codigo_cliente_omie": 12, "nome_fantasia": "Maria", "cnpj_cpf": "529.982.247-25"},
            ],
            2: [{"codigo_cliente_omie": 13, "razao_social": "Sem Doc", "cnpj_cpf": ""}],
        }[page]
        return httpx.Response(200, json={"total_de_paginas": 2, "clientes_cadastro": rows})

    payees = await _omie(handler).pull_payees()
    assert [p.external_id for p in payees] == ["11", "12", "13"]
    assert payees[0].tax_id == "11222333000181" and payees[0].tax_id_type == "cnpj"
    assert payees[1].tax_id_type == "cpf"
    assert payees[2].tax_id is None


@pytest.mark.asyncio
async def test_omie_pull_chart_maps_nature_and_skips_inactive():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "total_de_paginas": 1,
                "categoria_cadastro": [
                    {"codigo": "1.01", "descricao": "Vendas", "conta_receita": "S"},
                    {"codigo": "2.01", "descricao": "Aluguel", "conta_despesa": "S"},
                    {"codigo": "9.99", "descricao": "Velha", "conta_despesa": "S", "conta_inativa": "S"},
                ],
            },
        )

    accounts = await _omie(handler).pull_chart_of_accounts()
    assert [(a.code, a.nature) for a in accounts] == [("1.01", "revenue"), ("2.01", "expense")]


@pytest.mark.asyncio
async def test_omie_push_invoices_routes_by_direction_and_is_idempotent():
    import json

    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append((str(request.url), body["call"], body["param"][0]))
        if body["param"][0]["codigo_lancamento_integracao"] == integration_code("dup-0000-0000-0000-0000"):
            return httpx.Response(500, json={"faultstring": "Lançamento já cadastrado para o Código de Integração"})
        if body["param"][0]["codigo_lancamento_integracao"] == integration_code("bad"):
            return httpx.Response(500, json={"faultstring": "Categoria inexistente"})
        return httpx.Response(200, json={"codigo_status": "0"})

    due = date(2026, 11, 5)
    invoices = [
        ErpInvoice("rec-1", "receivable", Decimal("100.50"), due, payee_external_id="11"),
        ErpInvoice("pay-1", "payable", Decimal("40"), due, payee_external_id="12"),
        ErpInvoice("dup-0000-0000-0000-0000", "payable", Decimal("1"), due, payee_external_id="12"),
        ErpInvoice("bad", "payable", Decimal("1"), due, payee_external_id="12"),
        ErpInvoice("nopayee", "payable", Decimal("1"), due),
        ErpInvoice("paid", "payable", Decimal("1"), due, payee_external_id="12", status="paid"),
    ]
    result = await _omie(handler, default_category_code="1.01", default_account_id=7).push_invoices(invoices)

    assert result.created == 2
    assert result.skipped == 2  # duplicado + não-aberta
    assert len(result.errors) == 2
    assert set(result.synced_external_ids) == {"rec-1", "pay-1", "dup-0000-0000-0000-0000"}
    url, call, param = calls[0]
    assert url.endswith("/financas/contareceber/") and call == "IncluirContaReceber"
    assert param["data_vencimento"] == "05/11/2026"
    assert param["valor_documento"] == 100.5
    assert param["codigo_cliente_fornecedor"] == 11
    assert param["id_conta_corrente"] == 7
    assert calls[1][0].endswith("/financas/contapagar/") and calls[1][1] == "IncluirContaPagar"


def test_omie_integration_code_fits_omie_limit():
    assert len(integration_code(str(uuid.uuid4()))) == 20


@pytest.mark.asyncio
async def test_omie_throttles_between_calls():
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    def handler(request):
        return httpx.Response(200, json={})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    c = OmieConnector(client=client, min_interval=0.35, **CREDS)
    with patch("app.erp.omie.asyncio.sleep", fake_sleep):
        await c.test_connection()
        await c.test_connection()
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 0.35


@pytest.mark.asyncio
async def test_omie_network_error_becomes_erp_error():
    def handler(request):
        raise httpx.ConnectError("boom")

    with pytest.raises(ErpError):
        await _omie(handler)._call("geral/empresas", "ListarEmpresas", {})


# ────────────────────────────────────────────────────────────────────────────
# Serviço: criptografia, mapeamento, execuções
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_credentials_are_encrypted_at_rest(session, test_user, test_workspace):
    conn = await _connection(session, test_workspace, test_user.id)
    assert "KEY123" not in conn.credentials_enc and "SECRET456" not in conn.credentials_enc
    assert erp_service.read_credentials(conn) == CREDS


@pytest.mark.asyncio
async def test_create_connection_validates_provider_and_credentials(session, test_workspace):
    with pytest.raises(erp_service.ErpServiceError):
        await erp_service.create_connection(session, test_workspace.id, "sap", CREDS)
    with pytest.raises(erp_service.ErpServiceError):
        await erp_service.create_connection(session, test_workspace.id, "omie", {"app_key": "x"})


@pytest.mark.asyncio
async def test_pull_accounts_creates_then_updates_without_duplicating(
    session, test_user, test_workspace, fake_connector
):
    conn = await _connection(session, test_workspace, test_user.id)
    fake_connector.accounts = [
        ErpAccount("1.01", "1.01", "Vendas", "revenue"),
        ErpAccount("2.01", "2.01", "Aluguel", "expense"),
    ]
    run = await erp_service.sync_chart_of_accounts(session, conn.id)
    assert (run.status, run.created_count, run.updated_count, run.direction) == ("success", 2, 0, "pull")

    # Segunda rodada: nada novo, um nome mudou.
    fake_connector.accounts = [
        ErpAccount("1.01", "1.01", "Vendas de produtos", "revenue"),
        ErpAccount("2.01", "2.01", "Aluguel", "expense"),
    ]
    run2 = await erp_service.sync_chart_of_accounts(session, conn.id)
    assert (run2.created_count, run2.updated_count) == (0, 1)

    cats = (
        await session.execute(select(Category).where(Category.workspace_id == test_workspace.id))
    ).scalars().all()
    assert sorted(c.name for c in cats if c.name != "") .count("Vendas de produtos") == 1
    maps = await erp_service.list_mappings(session, conn.id, "category")
    assert len(maps) == 2


@pytest.mark.asyncio
async def test_pull_accounts_links_existing_category_by_name(
    session, test_user, test_workspace, fake_connector
):
    existing = Category(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id, name="Vendas"
    )
    session.add(existing)
    await session.flush()
    conn = await _connection(session, test_workspace, test_user.id)
    fake_connector.accounts = [ErpAccount("1.01", "1.01", "vendas", "revenue")]

    run = await erp_service.sync_chart_of_accounts(session, conn.id)
    assert run.created_count == 0
    mapping = await erp_service.get_mapping_by_external(session, conn.id, "category", "1.01")
    assert mapping.local_id == existing.id


@pytest.mark.asyncio
async def test_pull_payees_creates_tax_id_and_is_idempotent(
    session, test_user, test_workspace, fake_connector
):
    conn = await _connection(session, test_workspace, test_user.id)
    fake_connector.payees = [ErpPayee("11", "ACME LTDA", "11222333000181", "cnpj")]

    await erp_service.sync_payees(session, conn.id)
    run2 = await erp_service.sync_payees(session, conn.id)
    assert (run2.created_count, run2.updated_count) == (0, 0)

    payees = (
        await session.execute(select(Payee).where(Payee.workspace_id == test_workspace.id))
    ).scalars().all()
    assert [p.name for p in payees] == ["ACME LTDA"]
    assert payees[0].source == "erp" and payees[0].type == "company"
    tax = (await session.execute(select(PayeeTaxId))).scalars().all()
    assert [(t.kind, t.value) for t in tax] == [("cnpj", "11222333000181")]


@pytest.mark.asyncio
async def test_mapping_link_is_idempotent_and_unique(session, test_user, test_workspace):
    conn = await _connection(session, test_workspace, test_user.id)
    local = uuid.uuid4()
    first = await erp_service.link_entity(session, conn, "payee", local, "77")
    again = await erp_service.link_entity(session, conn, "payee", local, "77")
    assert first.id == again.id
    count = (
        await session.execute(
            select(ErpEntityMapping).where(ErpEntityMapping.connection_id == conn.id)
        )
    ).scalars().all()
    assert len(count) == 1
    with pytest.raises(erp_service.ErpServiceError):
        await erp_service.link_entity(session, conn, "bogus", local, "1")


async def _open_invoice(session, ws, user_id, payee_id=None):
    inv = Invoice(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        user_id=user_id,
        payee_id=payee_id,
        direction="receivable",
        status="open",
        number=1,
        series="A",
        issue_date=date(2026, 10, 1),
        due_date=date(2026, 10, 20),
        currency="BRL",
        subtotal=Decimal("500"),
        total=Decimal("500"),
    )
    session.add(inv)
    await session.flush()
    return inv


@pytest.mark.asyncio
async def test_push_invoices_records_mapping_and_skips_already_pushed(
    session, test_user, test_workspace, fake_connector
):
    payee = Payee(
        id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id, name="Cliente X"
    )
    session.add(payee)
    await session.flush()
    conn = await _connection(session, test_workspace, test_user.id)
    await erp_service.link_entity(session, conn, "payee", payee.id, "11")
    inv = await _open_invoice(session, test_workspace, test_user.id, payee.id)

    run = await erp_service.push_invoices(session, conn.id, date(2026, 10, 1), date(2026, 10, 31))
    assert (run.status, run.created_count, run.direction) == ("success", 1, "push")
    assert fake_connector.pushed_invoices[0].payee_external_id == "11"
    assert fake_connector.pushed_invoices[0].amount == Decimal("500")
    assert await erp_service.get_mapping_by_local(session, conn.id, "invoice", inv.id)

    fake_connector.pushed_invoices = []
    run2 = await erp_service.push_invoices(session, conn.id)
    assert run2.created_count == 0 and fake_connector.pushed_invoices == []


@pytest.mark.asyncio
async def test_push_invoices_item_error_is_recorded_not_mapped(
    session, test_user, test_workspace, fake_connector
):
    conn = await _connection(session, test_workspace, test_user.id)
    inv = await _open_invoice(session, test_workspace, test_user.id)
    fake_connector.invoice_result = SyncResult(errors=[f"{inv.id}: falta cliente"])

    run = await erp_service.push_invoices(session, conn.id)
    assert run.status == "error" and run.error_count == 1
    assert await erp_service.get_mapping_by_local(session, conn.id, "invoice", inv.id) is None


@pytest.mark.asyncio
async def test_failed_run_is_recorded_on_run_and_connection(session, test_user, test_workspace):
    conn = await _connection(session, test_workspace, test_user.id)

    class Boom(FakeConnector):
        async def pull_payees(self):
            raise ErpError("Omie fora do ar")

    with patch.object(erp_service, "build_connector", lambda c: Boom()):
        run = await erp_service.sync_payees(session, conn.id)

    assert run.status == "error" and run.errors == ["Omie fora do ar"]
    assert conn.last_sync_status == "error" and conn.last_sync_error == "Omie fora do ar"
    history = await erp_service.get_sync_history(session, conn.id)
    assert [r.id for r in history] == [run.id]


@pytest.mark.asyncio
async def test_contaazul_sync_records_not_implemented(session, test_user, test_workspace):
    conn = await erp_service.create_connection(
        session, test_workspace.id, "contaazul", {}, created_by_user_id=test_user.id
    )
    run = await erp_service.sync_payees(session, conn.id)
    assert run.status == "error" and "coming soon" in run.errors[0]
    result = await erp_service.test_connection(session, conn.id)
    assert result["ok"] is False and "coming soon" in result["message"]


@pytest.mark.asyncio
async def test_success_updates_connection_summary(session, test_user, test_workspace, fake_connector):
    conn = await _connection(session, test_workspace, test_user.id)
    fake_connector.payees = [ErpPayee("1", "Fulano")]
    await erp_service.sync_payees(session, conn.id)
    assert conn.last_sync_status == "success"
    assert conn.last_sync_at is not None and conn.last_sync_error is None


# ────────────────────────────────────────────────────────────────────────────
# API
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def ws_headers(auth_headers, test_workspace):
    return {**auth_headers, "X-Workspace-Id": str(test_workspace.id)}


@pytest.mark.asyncio
async def test_api_connection_crud_never_returns_credentials(client, ws_headers):
    r = await client.get("/api/erp/providers", headers=ws_headers)
    assert r.status_code == 200
    by_key = {p["key"]: p["available"] for p in r.json()}
    assert by_key == {"omie": True, "contaazul": False}

    r = await client.post(
        "/api/erp/connections",
        json={"provider": "omie", "credentials": CREDS, "sync_config": {"default_category_code": "1.01"}},
        headers=ws_headers,
    )
    assert r.status_code == 201, r.text
    assert "KEY123" not in r.text and "credentials" not in r.json()
    conn_id = r.json()["id"]

    r = await client.get("/api/erp/connections", headers=ws_headers)
    assert [c["id"] for c in r.json()] == [conn_id]
    r = await client.get(f"/api/erp/connections/{conn_id}", headers=ws_headers)
    assert r.json()["sync_config"] == {"default_category_code": "1.01"}

    r = await client.patch(
        f"/api/erp/connections/{conn_id}",
        json={"is_active": False, "credentials": {"app_key": "N", "app_secret": "M"}},
        headers=ws_headers,
    )
    assert r.status_code == 200 and r.json()["is_active"] is False

    r = await client.delete(f"/api/erp/connections/{conn_id}", headers=ws_headers)
    assert r.status_code == 204
    r = await client.get(f"/api/erp/connections/{conn_id}", headers=ws_headers)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_api_rejects_bad_provider_and_incomplete_credentials(client, ws_headers):
    r = await client.post(
        "/api/erp/connections", json={"provider": "sap", "credentials": {}}, headers=ws_headers
    )
    assert r.status_code == 422
    r = await client.post(
        "/api/erp/connections",
        json={"provider": "omie", "credentials": {"app_key": "x"}},
        headers=ws_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_api_test_endpoint_and_sync_queues_task(client, ws_headers):
    r = await client.post(
        "/api/erp/connections", json={"provider": "contaazul", "credentials": {}}, headers=ws_headers
    )
    conn_id = r.json()["id"]
    r = await client.post(f"/api/erp/connections/{conn_id}/test", headers=ws_headers)
    assert r.status_code == 200 and r.json()["ok"] is False

    fake_task = MagicMock()
    with patch("app.tasks.erp_tasks.sync_erp_connection", fake_task):
        r = await client.post(
            f"/api/erp/connections/{conn_id}/sync",
            json={"entity_type": "invoice", "date_from": "2026-10-01"},
            headers=ws_headers,
        )
        assert r.status_code == 202, r.text
        assert r.json()["direction"] == "push"
        fake_task.delay.assert_called_once_with(conn_id, "invoice", "2026-10-01", None)

        r = await client.post(
            f"/api/erp/connections/{conn_id}/sync",
            json={"entity_type": "payee", "direction": "push"},
            headers=ws_headers,
        )
        assert r.status_code == 422
        r = await client.post(
            f"/api/erp/connections/{conn_id}/sync", json={"entity_type": "nope"}, headers=ws_headers
        )
        assert r.status_code == 422

    r = await client.get(f"/api/erp/connections/{conn_id}", headers=ws_headers)
    assert r.json()["last_sync_status"] == "running"
    r = await client.get(f"/api/erp/connections/{conn_id}/history", headers=ws_headers)
    assert r.status_code == 200 and r.json() == []
    r = await client.get(f"/api/erp/connections/{conn_id}/mappings", headers=ws_headers)
    assert r.status_code == 200 and r.json() == []


@pytest.mark.asyncio
async def test_api_viewer_cannot_manage_or_read(client, viewer_auth_headers):
    r = await client.post(
        "/api/erp/connections",
        json={"provider": "omie", "credentials": CREDS},
        headers=viewer_auth_headers,
    )
    assert r.status_code == 403
    r = await client.get("/api/erp/connections", headers=viewer_auth_headers)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_api_connection_is_scoped_to_its_workspace(client, ws_headers, session, test_user):
    other = Workspace(id=uuid.uuid4(), name="Outra", kind="business", locale="pt-BR")
    session.add(other)
    await session.flush()
    conn = await erp_service.create_connection(session, other.id, "omie", dict(CREDS))
    await session.commit()
    r = await client.get(f"/api/erp/connections/{conn.id}", headers=ws_headers)
    assert r.status_code == 404
