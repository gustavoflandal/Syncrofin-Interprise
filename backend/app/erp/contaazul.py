"""Conta Azul — esqueleto (F3).

A API do Conta Azul usa OAuth2 (authorization code), o que pede um fluxo de consentimento no
navegador e renovação de token; isso fica para uma entrega própria. Registrado agora para que o
provedor apareça na UI e o contrato seja exercitado.
"""
from __future__ import annotations

from app.erp.base import ErpAccount, ErpInvoice, ErpPayee, ErpTransaction, SyncResult
from app.erp.registry import register_connector

COMING_SOON = "Conta Azul integration coming soon"


class ContaAzulConnector:
    name = "contaazul"

    def __init__(self, **_credentials) -> None:
        self.last_message: str | None = None

    async def test_connection(self) -> bool:
        self.last_message = COMING_SOON
        return False

    async def pull_chart_of_accounts(self) -> list[ErpAccount]:
        raise NotImplementedError(COMING_SOON)

    async def pull_payees(self) -> list[ErpPayee]:
        raise NotImplementedError(COMING_SOON)

    async def push_transactions(self, transactions: list[ErpTransaction]) -> SyncResult:
        raise NotImplementedError(COMING_SOON)

    async def push_invoices(self, invoices: list[ErpInvoice]) -> SyncResult:
        raise NotImplementedError(COMING_SOON)


register_connector("contaazul", ContaAzulConnector)
