"""Serviço de emissão de NF-e via provedor externo (B1).

Responsabilidades:
  - Gerenciar FiscalProviderConfig (salvar/ler credenciais)
  - Criar e atualizar FiscalEmission
  - Orquestrar emit / check_status / cancel via protocolo FiscalEmissionProvider
  - Construir o payload NF-e a partir de um Invoice

Não emite diretamente: delega ao adaptador do provedor configurado no workspace.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.services.crypto import decrypt, encrypt
from app.fiscal.emission_provider import EmissionResult, get_provider
from app.models.fiscal_emission import FiscalEmission, FiscalProviderConfig
from app.models.invoice import Invoice, InvoiceSettings
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


# ────────────────────────────────────────────────────────────────────────────
# Erros de domínio
# ────────────────────────────────────────────────────────────────────────────

class FiscalError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# ────────────────────────────────────────────────────────────────────────────
# Configuração do provedor
# ────────────────────────────────────────────────────────────────────────────

async def get_provider_config(
    session: AsyncSession,
    workspace_id: uuid.UUID,
) -> Optional[FiscalProviderConfig]:
    result = await session.execute(
        select(FiscalProviderConfig).where(FiscalProviderConfig.workspace_id == workspace_id)
    )
    return result.scalar_one_or_none()


async def save_provider_config(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    provider: str,
    api_key: str,
    environment: str,
    cnpj_emitente: Optional[str] = None,
    serie_padrao: str = "1",
) -> FiscalProviderConfig:
    existing = await get_provider_config(session, workspace_id)
    encrypted = encrypt(api_key)
    if not encrypted:
        raise FiscalError("encrypt_failed", "Falha ao cifrar chave de API")

    if existing:
        existing.provider = provider
        existing.api_key_encrypted = encrypted
        existing.environment = environment
        existing.cnpj_emitente = cnpj_emitente
        existing.serie_padrao = serie_padrao
        existing.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return existing

    config = FiscalProviderConfig(
        workspace_id=workspace_id,
        provider=provider,
        api_key_encrypted=encrypted,
        environment=environment,
        cnpj_emitente=cnpj_emitente,
        serie_padrao=serie_padrao,
    )
    session.add(config)
    await session.flush()
    return config


# ────────────────────────────────────────────────────────────────────────────
# Listagem de emissões
# ────────────────────────────────────────────────────────────────────────────

async def list_emissions(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    invoice_id: Optional[uuid.UUID] = None,
    limit: int = 50,
) -> list[FiscalEmission]:
    q = select(FiscalEmission).where(FiscalEmission.workspace_id == workspace_id)
    if invoice_id:
        q = q.where(FiscalEmission.invoice_id == invoice_id)
    q = q.order_by(FiscalEmission.created_at.desc()).limit(limit)
    result = await session.execute(q)
    return list(result.scalars())


async def get_emission(
    session: AsyncSession,
    emission_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Optional[FiscalEmission]:
    result = await session.execute(
        select(FiscalEmission).where(
            FiscalEmission.id == emission_id,
            FiscalEmission.workspace_id == workspace_id,
        )
    )
    return result.scalar_one_or_none()


# ────────────────────────────────────────────────────────────────────────────
# Construção do payload NF-e para Focus NFe
# ────────────────────────────────────────────────────────────────────────────

def _build_nfe_payload(
    invoice: Invoice,
    config: FiscalProviderConfig,
) -> dict:
    """Monta o payload JSON no formato Focus NFe v2 para NF-e modelo 55.

    Campos obrigatórios mínimos para emissão em homologação. Campos de
    endereço, transporte, etc. precisam estar no `snapshot` ou `custom_fields`
    da fatura — o serviço os mescla quando presentes.
    """
    snapshot = invoice.snapshot or {}
    custom = invoice.custom_fields or {}

    # Tomador = payee da fatura
    payee_snap = snapshot.get("payee") or {}
    tax_ids_snap = payee_snap.get("tax_ids") or []
    cnpj_tomador = next(
        (t["value"] for t in tax_ids_snap if t.get("kind") == "cnpj"),
        custom.get("cnpj_tomador", ""),
    )
    cpf_tomador = next(
        (t["value"] for t in tax_ids_snap if t.get("kind") == "cpf"),
        custom.get("cpf_tomador", ""),
    )

    items = []
    for i, line in enumerate(invoice.lines, start=1):
        item: dict = {
            "numero_item": str(i),
            "codigo_produto": custom.get(f"item_{i}_codigo") or str(i).zfill(3),
            "descricao": line.description[:120],
            "cfop": custom.get("cfop") or "5102",
            "unidade_comercial": (line.unit or "UN").upper()[:6],
            "quantidade_comercial": str(line.quantity),
            "valor_unitario_comercial": str(line.unit_price),
            "valor_bruto": str(line.total),
            "unidade_tributavel": (line.unit or "UN").upper()[:6],
            "quantidade_tributavel": str(line.quantity),
            "valor_unitario_tributavel": str(line.unit_price),
            "icms_modalidade": "102",  # simples nacional — sem ICMS
            "pis_modalidade": "07",     # isento
            "cofins_modalidade": "07",  # isento
        }
        items.append(item)

    # Fallback: se não houver linhas, gera um item sintético com o total
    if not items:
        items = [{
            "numero_item": "1",
            "codigo_produto": "001",
            "descricao": (invoice.notes or f"Fatura {invoice.external_number or invoice.number}")[: 120],
            "cfop": custom.get("cfop") or "5102",
            "unidade_comercial": "SV",
            "quantidade_comercial": "1",
            "valor_unitario_comercial": str(invoice.total),
            "valor_bruto": str(invoice.total),
            "unidade_tributavel": "SV",
            "quantidade_tributavel": "1",
            "valor_unitario_tributavel": str(invoice.total),
            "icms_modalidade": "102",
            "pis_modalidade": "07",
            "cofins_modalidade": "07",
        }]

    payload: dict = {
        "natureza_operacao": custom.get("natureza_operacao") or "Prestação de serviços",
        "forma_pagamento": 0,
        "modelo": 55,
        "serie": config.serie_padrao,
        "data_emissao": invoice.issue_date.isoformat(),
        "data_entrada_saida": invoice.issue_date.isoformat(),
        "tipo_documento": 1,  # saída
        "local_destino": 1,   # operação interna
        "finalidade_emissao": 1,  # NF-e normal
        "consumidor_final": custom.get("consumidor_final", 1),
        "presenca_comprador": custom.get("presenca_comprador", 9),  # outros
        "emitente": {
            "cnpj": (config.cnpj_emitente or "").replace(".", "").replace("/", "").replace("-", ""),
            "nome": snapshot.get("issuer", {}).get("name") or "",
            "regime_tributario": custom.get("regime_tributario", 1),  # 1=Simples
        },
        "items": items,
        "informacoes_adicionais_contribuinte": invoice.notes or "",
    }

    # Tomador: CNPJ ou CPF
    if cnpj_tomador:
        payload["destinatario"] = {
            "cnpj": cnpj_tomador.replace(".", "").replace("/", "").replace("-", ""),
            "nome": payee_snap.get("name") or custom.get("nome_tomador") or "Consumidor final",
            "email": payee_snap.get("email") or custom.get("email_tomador") or "",
        }
    elif cpf_tomador:
        payload["destinatario"] = {
            "cpf": cpf_tomador.replace(".", "").replace("-", ""),
            "nome": payee_snap.get("name") or custom.get("nome_tomador") or "Consumidor final",
            "email": payee_snap.get("email") or custom.get("email_tomador") or "",
        }

    # Campos extras fornecidos pelo workspace via custom_fields da fatura
    if custom.get("informacoes_adicionais"):
        payload["informacoes_adicionais_contribuinte"] = custom["informacoes_adicionais"]

    return payload


# ────────────────────────────────────────────────────────────────────────────
# Operações de emissão
# ────────────────────────────────────────────────────────────────────────────

def _apply_result(emission: FiscalEmission, result: EmissionResult) -> None:
    emission.status = result.status
    emission.provider_ref = result.provider_ref
    if result.chave_acesso:
        emission.chave_acesso = result.chave_acesso
    if result.nfe_number:
        emission.nfe_number = result.nfe_number
    if result.nfe_serie:
        emission.nfe_serie = result.nfe_serie
    if result.xml_url:
        emission.xml_url = result.xml_url
    if result.pdf_url:
        emission.pdf_url = result.pdf_url
    emission.error_message = result.error_message
    emission.error_code = result.error_code
    emission.updated_at = datetime.now(timezone.utc)


async def emit_nfe(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    invoice: Invoice,
) -> FiscalEmission:
    """Inicia a emissão de NF-e para uma fatura.

    Cria o registro de emissão, chama o provedor e persiste o resultado.
    Se a fatura já tem uma emissão `issued`, levanta FiscalError.
    """
    config = await get_provider_config(session, workspace_id)
    if not config:
        raise FiscalError(
            "no_provider_config",
            "Configure o provedor de NF-e nas configurações do workspace antes de emitir.",
            400,
        )

    # Verifica se já existe emissão ativa para esta fatura
    result_existing = await session.execute(
        select(FiscalEmission).where(
            FiscalEmission.invoice_id == invoice.id,
            FiscalEmission.workspace_id == workspace_id,
            FiscalEmission.status == "issued",
        )
    )
    if result_existing.scalar_one_or_none():
        raise FiscalError("already_issued", "Esta fatura já foi emitida.", 409)

    if invoice.status not in ("open", "draft"):
        raise FiscalError("invoice_not_open", "Apenas faturas abertas ou rascunhos podem ser emitidas.", 400)

    provider_ref = str(uuid.uuid4())
    emission = FiscalEmission(
        workspace_id=workspace_id,
        invoice_id=invoice.id,
        provider=config.provider,
        environment=config.environment,
        status="pending",
        provider_ref=provider_ref,
    )
    session.add(emission)
    await session.flush()

    try:
        payload = _build_nfe_payload(invoice, config)
        provider = get_provider(config)
        api_result = await provider.emit(config, payload, provider_ref)
    except NotImplementedError as exc:
        emission.status = "error"
        emission.error_message = str(exc)
        await session.flush()
        await session.commit()
        raise FiscalError("provider_not_implemented", str(exc), 501) from exc
    except Exception as exc:
        emission.status = "error"
        emission.error_message = f"Erro ao contactar provedor: {exc}"
        await session.flush()
        await session.commit()
        raise FiscalError("provider_error", emission.error_message, 502) from exc

    _apply_result(emission, api_result)
    await session.flush()
    await session.commit()

    # Download and store the fiscal XML/PDF locally as locked attachments
    # so they survive even if the provider goes away.
    if emission.status == "issued":
        await _store_fiscal_documents(session, emission, invoice, workspace_id)

    return emission


async def _store_fiscal_documents(
    session: AsyncSession,
    emission: FiscalEmission,
    invoice: Invoice,
    workspace_id: uuid.UUID,
) -> None:
    """Download XML and PDF from the provider and file them as locked attachments.

    Best-effort: a download failure is logged but does not undo the emission.
    """
    import httpx

    from app.services import invoice_attachment_service

    chave = emission.chave_acesso or emission.provider_ref or ""
    provider_name = emission.provider or "fiscal"

    for url, ext, content_type in [
        (emission.xml_url, "xml", "application/xml"),
        (emission.pdf_url, "pdf", "application/pdf"),
    ]:
        if not url:
            continue
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.content
        except Exception:
            logger.warning(
                "B6: failed to download fiscal %s from %s for invoice %s",
                ext,
                url,
                invoice.id,
                exc_info=True,
            )
            continue

        filename = f"nfe_{chave[:20]}.{ext}" if chave else f"nfe_{emission.id}.{ext}"
        try:
            await invoice_attachment_service.upload(
                session=session,
                workspace_id=workspace_id,
                user_id=None,
                invoice_id=invoice.id,
                filename=filename,
                content_type=content_type,
                data=data,
                kind="fiscal",
                source=provider_name,
                external_id=f"{chave}_{ext}" if chave else None,
                document_number=chave or None,
            )
        except Exception:
            logger.warning(
                "B6: failed to store fiscal %s for invoice %s",
                ext,
                invoice.id,
                exc_info=True,
            )


async def refresh_emission(
    session: AsyncSession,
    emission: FiscalEmission,
) -> FiscalEmission:
    """Consulta o status da emissão no provedor e atualiza o registro."""
    config = await get_provider_config(session, emission.workspace_id)
    if not config:
        raise FiscalError("no_provider_config", "Provedor não configurado.", 400)

    if emission.status in ("issued", "cancelled"):
        return emission  # estado terminal, não precisa consultar

    if not emission.provider_ref:
        raise FiscalError("no_provider_ref", "Emissão sem referência de provedor.", 400)

    provider = get_provider(config)
    try:
        api_result = await provider.check_status(config, emission.provider_ref)
    except Exception as exc:
        raise FiscalError("provider_error", f"Erro ao consultar provedor: {exc}", 502) from exc

    _apply_result(emission, api_result)
    await session.flush()
    await session.commit()
    return emission


async def cancel_emission(
    session: AsyncSession,
    emission: FiscalEmission,
    justificativa: str = "Cancelamento solicitado pelo emitente",
) -> FiscalEmission:
    """Solicita o cancelamento de uma NF-e já emitida."""
    if emission.status != "issued":
        raise FiscalError("not_issued", "Só é possível cancelar uma NF-e já autorizada.", 400)

    config = await get_provider_config(session, emission.workspace_id)
    if not config:
        raise FiscalError("no_provider_config", "Provedor não configurado.", 400)

    provider = get_provider(config)
    try:
        api_result = await provider.cancel(config, emission.provider_ref or "", justificativa)
    except Exception as exc:
        raise FiscalError("provider_error", f"Erro ao cancelar: {exc}", 502) from exc

    _apply_result(emission, api_result)
    await session.flush()
    await session.commit()
    return emission
