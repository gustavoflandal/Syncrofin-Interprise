"""Abstração do provedor de emissão de NF-e (B1).

Define o protocolo que todo adaptador deve cumprir e o tipo de resultado
comum a todos. Cada adaptador concreto fica em `app/fiscal/providers/`.

Princípio: o serviço de emissão (`fiscal_emission_service`) nunca importa
um adaptador diretamente — ele chama `get_provider(config)`, que devolve
o adaptador correto. Adicionar um provedor novo é apenas:
  1. Criar `providers/<nome>.py` implementando `FiscalEmissionProvider`.
  2. Registrar em `_PROVIDERS` abaixo.
  3. Adicionar o nome ao `SUPPORTED_PROVIDERS` em `models/fiscal_emission.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from app.models.fiscal_emission import FiscalProviderConfig


@dataclass
class EmissionResult:
    """Resultado normalizado de qualquer operação de emissão."""

    # Referência interna do provedor (usada para consultas subsequentes)
    provider_ref: str
    # Status após a operação ('processing', 'issued', 'error', 'cancelled')
    status: str
    chave_acesso: Optional[str] = None
    nfe_number: Optional[str] = None
    nfe_serie: Optional[str] = None
    xml_url: Optional[str] = None
    pdf_url: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    # Payload bruto do provedor para diagnóstico
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class FiscalEmissionProvider(Protocol):
    """Contrato que todo adaptador de provedor NF-e deve implementar."""

    async def emit(
        self,
        config: FiscalProviderConfig,
        invoice_data: dict[str, Any],
        provider_ref: str,
    ) -> EmissionResult:
        """Envia a NF-e ao provedor e retorna o resultado inicial.

        `invoice_data` é um dict com os campos que o provedor precisa
        (gerado por `fiscal_emission_service._build_nfe_payload`).
        `provider_ref` é um UUID string gerado pelo SyncroFin, usado como
        chave de idempotência nos provedores que suportam.
        """
        ...

    async def check_status(
        self,
        config: FiscalProviderConfig,
        provider_ref: str,
    ) -> EmissionResult:
        """Consulta o status de uma emissão já iniciada."""
        ...

    async def cancel(
        self,
        config: FiscalProviderConfig,
        provider_ref: str,
        justificativa: str = "Cancelamento solicitado pelo emitente",
    ) -> EmissionResult:
        """Solicita o cancelamento de uma NF-e já emitida."""
        ...


def get_provider(config: FiscalProviderConfig) -> FiscalEmissionProvider:
    """Retorna o adaptador para o provedor configurado no workspace."""
    from app.fiscal.providers.focus_nfe import FocusNfeProvider
    from app.fiscal.providers.enotas import EnotasProvider
    from app.fiscal.providers.plugnotas import PlugnotasProvider

    _PROVIDERS: dict[str, FiscalEmissionProvider] = {
        "focus_nfe": FocusNfeProvider(),
        "enotas": EnotasProvider(),
        "plugnotas": PlugnotasProvider(),
    }
    provider = _PROVIDERS.get(config.provider)
    if provider is None:
        raise ValueError(f"Provedor desconhecido: {config.provider}")
    return provider
