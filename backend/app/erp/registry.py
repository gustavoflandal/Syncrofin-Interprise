"""Registro de conectores ERP por nome (mesmo padrão de `app.fiscal` e `app.providers`)."""
from __future__ import annotations

from app.erp.base import ErpConnector

_CONNECTORS: dict[str, type] = {}


def register_connector(name: str, cls: type) -> None:
    _CONNECTORS[name] = cls


def get_connector(name: str, **kwargs) -> ErpConnector:
    cls = _CONNECTORS.get(name)
    if cls is None:
        raise ValueError(f"Conector ERP desconhecido: {name}")
    return cls(**kwargs)


def available_connectors() -> list[str]:
    return sorted(_CONNECTORS)
