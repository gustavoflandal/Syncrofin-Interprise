"""Contrato dos conectores ERP/contábeis (F3).

Segue o mesmo desenho de `app.fiscal.emission_provider`: um Protocol pequeno, dataclasses neutras
(nada específico de um ERP vaza para o serviço) e um registro por nome em `app.erp.registry`.

Direção dos dados, de propósito assimétrica:
  - **pull**: plano de contas e cadastro de clientes/fornecedores vêm do ERP (ele é a fonte).
  - **push**: lançamentos e faturas saem do SyncroFin (ele é a fonte).
O conector não conhece mapeamento nem banco: devolve/recebe dados neutros e o serviço
(`erp_service`) cuida de idempotência e de `erp_entity_mappings`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol, runtime_checkable


class ErpError(Exception):
    """Falha ao falar com o ERP (credencial inválida, limite de uso, resposta inesperada)."""


@dataclass
class ErpAccount:
    external_id: str
    code: str
    name: str
    nature: str  # "revenue" | "expense" | "cost" | "asset" | "liability"
    parent_external_id: str | None = None


@dataclass
class ErpPayee:
    external_id: str
    name: str
    tax_id: str | None = None
    tax_id_type: str | None = None  # "cpf" | "cnpj"


@dataclass
class ErpTransaction:
    external_id: str
    date: date
    amount: Decimal
    type: str  # "debit" | "credit"
    description: str
    account_code: str | None = None
    payee_external_id: str | None = None
    category_code: str | None = None


@dataclass
class ErpInvoice:
    external_id: str
    direction: str  # "receivable" | "payable"
    amount: Decimal
    due_date: date
    payee_external_id: str | None = None
    description: str = ""
    status: str = "open"
    category_code: str | None = None


@dataclass
class SyncResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    #: external_id (o do SyncroFin) de cada item que o ERP agora tem, seja porque criou ou porque
    #: já existia. É o que o serviço usa para gravar o mapeamento; um item com erro fica de fora.
    synced_external_ids: list[str] = field(default_factory=list)


@runtime_checkable
class ErpConnector(Protocol):
    name: str

    async def test_connection(self) -> bool: ...

    async def pull_chart_of_accounts(self) -> list[ErpAccount]: ...

    async def pull_payees(self) -> list[ErpPayee]: ...

    async def push_transactions(self, transactions: list[ErpTransaction]) -> SyncResult: ...

    async def push_invoices(self, invoices: list[ErpInvoice]) -> SyncResult: ...
