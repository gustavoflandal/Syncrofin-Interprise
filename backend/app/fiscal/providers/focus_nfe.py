"""Adaptador Focus NFe (https://focusnfe.com.br).

Documentação: https://focusnfe.com.br/doc/

Autenticação: HTTP Basic com `api_key` como usuário e senha vazia.
Endpoint base:
  - Homologação: https://homologacao.focusnfe.com.br
  - Produção:    https://api.focusnfe.com.br

Fluxo de emissão:
  1. POST /v2/nfe?ref={ref}   → 202 accepted  (processing) ou 200 (issued)
  2. GET  /v2/nfe/{ref}       → status e dados
  3. DELETE /v2/nfe/{ref}     → cancelamento

O campo `ref` é a referência do SyncroFin (UUID). Idempotente: reenviar
o mesmo `ref` devolve o resultado anterior em vez de duplicar.
"""
from __future__ import annotations

import httpx

from app.agents.services.crypto import decrypt
from app.fiscal.emission_provider import EmissionResult
from app.models.fiscal_emission import FiscalProviderConfig

_BASE_URLS = {
    "homologation": "https://homologacao.focusnfe.com.br",
    "production": "https://api.focusnfe.com.br",
}

_TIMEOUT = 30.0  # segundos


def _base_url(config: FiscalProviderConfig) -> str:
    return _BASE_URLS.get(config.environment, _BASE_URLS["homologation"])


def _api_key(config: FiscalProviderConfig) -> str:
    key = decrypt(config.api_key_encrypted)
    if not key:
        raise ValueError("Chave de API do Focus NFe não configurada ou corrompida")
    return key


def _parse_result(data: dict, provider_ref: str) -> EmissionResult:
    """Normaliza a resposta do Focus NFe para EmissionResult."""
    status_map = {
        "autorizado": "issued",
        "cancelado": "cancelled",
        "processando_autorizacao": "processing",
        "erro_autorizacao": "error",
        "denegado": "error",
    }
    raw_status = data.get("status", "")
    status = status_map.get(raw_status, "processing")

    nfe = data.get("nfe", {}) or {}
    chave = nfe.get("chave_nfe") or data.get("chave_nfe")
    number = str(nfe.get("numero") or data.get("numero") or "")
    serie = str(nfe.get("serie") or data.get("serie") or "")
    xml_url = data.get("caminho_xml_nota_fiscal")
    pdf_url = data.get("caminho_danfe")

    error_message = None
    error_code = None
    if status == "error":
        erros = data.get("erros") or []
        if erros:
            first = erros[0] if isinstance(erros[0], dict) else {}
            error_code = str(first.get("codigo", ""))
            error_message = str(first.get("mensagem", raw_status))
        else:
            error_message = data.get("mensagem_sefaz") or raw_status

    return EmissionResult(
        provider_ref=provider_ref,
        status=status,
        chave_acesso=chave,
        nfe_number=number or None,
        nfe_serie=serie or None,
        xml_url=xml_url,
        pdf_url=pdf_url,
        error_message=error_message,
        error_code=error_code,
        raw=data,
    )


class FocusNfeProvider:
    """Implementação do protocolo FiscalEmissionProvider para Focus NFe."""

    async def emit(
        self,
        config: FiscalProviderConfig,
        invoice_data: dict,
        provider_ref: str,
    ) -> EmissionResult:
        url = f"{_base_url(config)}/v2/nfe"
        params = {"ref": provider_ref}
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                url,
                json=invoice_data,
                params=params,
                auth=(_api_key(config), ""),
            )
        data = resp.json() if resp.content else {}
        # 200 = authorized, 202 = processing, 422 = rejected
        if resp.status_code == 422:
            erros = data.get("erros", [])
            msg = erros[0].get("mensagem", str(data)) if erros else str(data)
            return EmissionResult(
                provider_ref=provider_ref,
                status="error",
                error_message=msg,
                raw=data,
            )
        if resp.status_code not in (200, 201, 202):
            return EmissionResult(
                provider_ref=provider_ref,
                status="error",
                error_message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                raw=data,
            )
        return _parse_result(data, provider_ref)

    async def check_status(
        self,
        config: FiscalProviderConfig,
        provider_ref: str,
    ) -> EmissionResult:
        url = f"{_base_url(config)}/v2/nfe/{provider_ref}"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, auth=(_api_key(config), ""))
        data = resp.json() if resp.content else {}
        if resp.status_code == 404:
            return EmissionResult(
                provider_ref=provider_ref,
                status="error",
                error_message="Emissão não encontrada no provedor",
                raw=data,
            )
        return _parse_result(data, provider_ref)

    async def cancel(
        self,
        config: FiscalProviderConfig,
        provider_ref: str,
        justificativa: str = "Cancelamento solicitado pelo emitente",
    ) -> EmissionResult:
        url = f"{_base_url(config)}/v2/nfe/{provider_ref}"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.delete(
                url,
                json={"justificativa": justificativa},
                auth=(_api_key(config), ""),
            )
        data = resp.json() if resp.content else {}
        if resp.status_code not in (200, 204):
            return EmissionResult(
                provider_ref=provider_ref,
                status="error",
                error_message=f"Cancelamento falhou: HTTP {resp.status_code}",
                raw=data,
            )
        return EmissionResult(
            provider_ref=provider_ref,
            status="cancelled",
            raw=data,
        )
