"""Conector Omie (F3).

A API do Omie é JSON-RPC sobre POST: o corpo leva `call` (método), `app_key`, `app_secret` e
`param` (lista com um objeto). Erros voltam como `{"faultstring", "faultcode"}`, em geral com HTTP
500, então o corpo é lido independentemente do status.

Limite de uso: ~3 req/s por app. `_throttle` espaça as chamadas com `asyncio.sleep`; em testes
passe `min_interval=0`.

Desvio consciente do enunciado: "plano de contas" no Omie é o cadastro de **categorias**
(`geral/categorias`, `ListarCategorias`); `geral/contacorrente` lista contas bancárias, que não
são plano de contas.
"""
from __future__ import annotations

import asyncio
import re
import time
from datetime import date
from decimal import Decimal

import httpx

from app.erp.base import (
    ErpAccount,
    ErpError,
    ErpInvoice,
    ErpPayee,
    ErpTransaction,
    SyncResult,
)
from app.erp.registry import register_connector

BASE_URL = "https://app.omie.com.br/api/v1"
PAGE_SIZE = 100
# Teto de segurança: um cadastro com mais de 500 páginas é bug de paginação, não dado.
MAX_PAGES = 500

_DUPLICATE_RE = re.compile(r"j[aá]\s+(cadastrad|existe)|duplicad|already", re.I)


def _omie_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def integration_code(external_id: str) -> str:
    """`codigo_lancamento_integracao` aceita 20 caracteres; um UUID sem hífens truncado cabe."""
    return external_id.replace("-", "")[:20]


class OmieConnector:
    name = "omie"

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        default_category_code: str | None = None,
        default_account_id: int | str | None = None,
        client: httpx.AsyncClient | None = None,
        min_interval: float = 0.35,
        base_url: str = BASE_URL,
        **_ignored,
    ) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.default_category_code = default_category_code
        self.default_account_id = default_account_id
        self._client = client
        self._min_interval = min_interval
        self._base_url = base_url.rstrip("/")
        self._last_call = 0.0
        self.last_message: str | None = None

    async def _throttle(self) -> None:
        if self._min_interval <= 0:
            return
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = time.monotonic()

    async def _call(self, path: str, call: str, param: dict) -> dict:
        await self._throttle()
        body = {
            "call": call,
            "app_key": self.app_key,
            "app_secret": self.app_secret,
            "param": [param],
        }
        url = f"{self._base_url}/{path.strip('/')}/"
        try:
            if self._client is not None:
                resp = await self._client.post(url, json=body, timeout=30)
            else:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(url, json=body, timeout=30)
        except httpx.HTTPError as exc:
            raise ErpError(f"Omie indisponível: {exc}") from exc
        try:
            data = resp.json()
        except ValueError:
            raise ErpError(f"Resposta inválida do Omie (HTTP {resp.status_code})")
        if isinstance(data, dict) and data.get("faultstring"):
            raise ErpError(str(data["faultstring"]))
        if resp.status_code >= 400:
            raise ErpError(f"Omie respondeu HTTP {resp.status_code}")
        return data

    async def _paged(self, path: str, call: str, key: str, extra: dict | None = None) -> list[dict]:
        rows: list[dict] = []
        page = 1
        while page <= MAX_PAGES:
            param = {"pagina": page, "registros_por_pagina": PAGE_SIZE, **(extra or {})}
            data = await self._call(path, call, param)
            rows.extend(data.get(key) or [])
            if page >= int(data.get("total_de_paginas") or 1):
                break
            page += 1
        return rows

    async def test_connection(self) -> bool:
        try:
            await self._call(
                "geral/empresas", "ListarEmpresas", {"pagina": 1, "registros_por_pagina": 1}
            )
        except ErpError as exc:
            self.last_message = str(exc)
            return False
        return True

    async def pull_chart_of_accounts(self) -> list[ErpAccount]:
        rows = await self._paged("geral/categorias", "ListarCategorias", "categoria_cadastro")
        accounts: list[ErpAccount] = []
        for row in rows:
            code = str(row.get("codigo") or "").strip()
            if not code or row.get("conta_inativa") == "S":
                continue
            if row.get("conta_receita") == "S":
                nature = "revenue"
            elif row.get("conta_despesa") == "S":
                nature = "expense"
            else:
                nature = "asset"
            parent = str(row.get("categoria_superior") or "").strip() or None
            accounts.append(
                ErpAccount(
                    external_id=code,
                    code=code,
                    name=str(row.get("descricao") or code),
                    nature=nature,
                    parent_external_id=parent,
                )
            )
        return accounts

    async def pull_payees(self) -> list[ErpPayee]:
        rows = await self._paged(
            "geral/clientes",
            "ListarClientes",
            "clientes_cadastro",
            {"apenas_importado_api": "N"},
        )
        payees: list[ErpPayee] = []
        for row in rows:
            ext = row.get("codigo_cliente_omie")
            name = (row.get("razao_social") or row.get("nome_fantasia") or "").strip()
            if ext is None or not name:
                continue
            digits = re.sub(r"\D", "", str(row.get("cnpj_cpf") or ""))
            tax_type = None
            if len(digits) == 14:
                tax_type = "cnpj"
            elif len(digits) == 11:
                tax_type = "cpf"
            payees.append(
                ErpPayee(
                    external_id=str(ext),
                    name=name,
                    tax_id=digits if tax_type else None,
                    tax_id_type=tax_type,
                )
            )
        return payees

    async def push_transactions(self, transactions: list[ErpTransaction]) -> SyncResult:
        # O Omie não tem um "lançamento" genérico além de conta a pagar/receber ou movimento de
        # conta corrente; empurrar transações como títulos distorceria o contas a pagar. Fica
        # explícito em vez de silenciosamente errado: use o envio de faturas.
        if not transactions:
            return SyncResult()
        return SyncResult(
            skipped=len(transactions),
            errors=["Omie: envio de transações avulsas não suportado; use o envio de faturas"],
        )

    async def push_invoices(self, invoices: list[ErpInvoice]) -> SyncResult:
        result = SyncResult()
        for inv in invoices:
            if inv.status != "open":
                result.skipped += 1
                continue
            category = inv.category_code or self.default_category_code
            if not inv.payee_external_id or not category:
                result.errors.append(
                    f"{inv.external_id}: falta cliente/fornecedor sincronizado ou categoria padrão"
                )
                continue
            receivable = inv.direction == "receivable"
            path = "financas/contareceber" if receivable else "financas/contapagar"
            call = "IncluirContaReceber" if receivable else "IncluirContaPagar"
            param = {
                "codigo_lancamento_integracao": integration_code(inv.external_id),
                "codigo_cliente_fornecedor": int(inv.payee_external_id),
                "data_vencimento": _omie_date(inv.due_date),
                "data_previsao": _omie_date(inv.due_date),
                "valor_documento": float(Decimal(inv.amount)),
                "codigo_categoria": category,
                "observacao": inv.description[:500],
            }
            if self.default_account_id is not None:
                param["id_conta_corrente"] = int(self.default_account_id)
            try:
                await self._call(path, call, param)
                result.created += 1
                result.synced_external_ids.append(inv.external_id)
            except ErpError as exc:
                if _DUPLICATE_RE.search(str(exc)):
                    # Idempotência: o código de integração já existe, logo o título já está lá.
                    result.skipped += 1
                    result.synced_external_ids.append(inv.external_id)
                else:
                    result.errors.append(f"{inv.external_id}: {exc}")
        return result


register_connector("omie", OmieConnector)
