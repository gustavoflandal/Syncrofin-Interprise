"""Conectores ERP/contábeis (F3). Importar o pacote registra os conectores embutidos."""
from app.erp import contaazul, omie  # noqa: F401  (efeito colateral: registro)
from app.erp.base import (
    ErpAccount,
    ErpConnector,
    ErpError,
    ErpInvoice,
    ErpPayee,
    ErpTransaction,
    SyncResult,
)
from app.erp.registry import available_connectors, get_connector, register_connector

__all__ = [
    "ErpAccount",
    "ErpConnector",
    "ErpError",
    "ErpInvoice",
    "ErpPayee",
    "ErpTransaction",
    "SyncResult",
    "available_connectors",
    "get_connector",
    "register_connector",
]
