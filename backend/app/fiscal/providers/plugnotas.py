"""Adaptador PlugNotas (stub — implementação completa em sprint futuro)."""
from __future__ import annotations

from typing import Any

from app.fiscal.emission_provider import EmissionResult
from app.models.fiscal_emission import FiscalProviderConfig


class PlugnotasProvider:
    async def emit(self, config: FiscalProviderConfig, invoice_data: dict[str, Any], provider_ref: str) -> EmissionResult:
        raise NotImplementedError("Adaptador PlugNotas ainda não implementado. Use Focus NFe.")

    async def check_status(self, config: FiscalProviderConfig, provider_ref: str) -> EmissionResult:
        raise NotImplementedError("Adaptador PlugNotas ainda não implementado.")

    async def cancel(self, config: FiscalProviderConfig, provider_ref: str, justificativa: str = "") -> EmissionResult:
        raise NotImplementedError("Adaptador PlugNotas ainda não implementado.")
