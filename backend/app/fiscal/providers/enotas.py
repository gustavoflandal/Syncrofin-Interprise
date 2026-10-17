"""Adaptador eNotas (stub — implementação completa em sprint futuro).

A classe existe para que `get_provider` não falhe quando um workspace
seleciona este provedor. Toda operação levanta `NotImplementedError`
com mensagem amigável ao operador.
"""
from __future__ import annotations

from typing import Any

from app.fiscal.emission_provider import EmissionResult
from app.models.fiscal_emission import FiscalProviderConfig


class EnotasProvider:
    async def emit(self, config: FiscalProviderConfig, invoice_data: dict[str, Any], provider_ref: str) -> EmissionResult:
        raise NotImplementedError("Adaptador eNotas ainda não implementado. Use Focus NFe.")

    async def check_status(self, config: FiscalProviderConfig, provider_ref: str) -> EmissionResult:
        raise NotImplementedError("Adaptador eNotas ainda não implementado.")

    async def cancel(self, config: FiscalProviderConfig, provider_ref: str, justificativa: str = "") -> EmissionResult:
        raise NotImplementedError("Adaptador eNotas ainda não implementado.")
