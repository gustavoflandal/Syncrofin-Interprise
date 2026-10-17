"""API de emissão fiscal de NF-e (B1).

Rotas:
  GET/PUT /api/workspaces/{id}/fiscal/provider-config
  GET     /api/workspaces/{id}/fiscal/emissions
  POST    /api/workspaces/{id}/invoices/{inv_id}/emit-nfe
  POST    /api/workspaces/{id}/fiscal/emissions/{em_id}/refresh
  POST    /api/workspaces/{id}/fiscal/emissions/{em_id}/cancel
  POST    /api/fiscal/callback/{provider}   (sem auth — verificação por HMAC futuro)
"""
import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, current_workspace, require_permission
from app.schemas.fiscal_emission import (
    CancelEmissionRequest,
    FiscalEmissionRead,
    FiscalProviderConfigRead,
    FiscalProviderConfigSave,
)
from app.services import fiscal_emission_service
from app.services.fiscal_emission_service import FiscalError
from app.services.invoice_service import get_invoice

logger = logging.getLogger(__name__)

_emit_gate = require_permission("fiscal.emit")
_admin_gate = require_permission("fiscal.admin")

router = APIRouter(tags=["fiscal-emissions"])


# ────────────────────────────────────────────────────────────────────────────
# Configuração do provedor
# ────────────────────────────────────────────────────────────────────────────

@router.get("/api/workspaces/{workspace_id}/fiscal/provider-config", response_model=FiscalProviderConfigRead)
async def get_fiscal_config(
    workspace_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    config = await fiscal_emission_service.get_provider_config(session, workspace_id)
    if not config:
        raise HTTPException(status_code=404, detail="Provedor fiscal não configurado")
    return FiscalProviderConfigRead(
        workspace_id=config.workspace_id,
        provider=config.provider,
        environment=config.environment,
        cnpj_emitente=config.cnpj_emitente,
        serie_padrao=config.serie_padrao,
        has_api_key=bool(config.api_key_encrypted),
        updated_at=config.updated_at,
    )


@router.put(
    "/api/workspaces/{workspace_id}/fiscal/provider-config",
    response_model=FiscalProviderConfigRead,
    status_code=200,
)
async def save_fiscal_config(
    workspace_id: uuid.UUID,
    data: FiscalProviderConfigSave,
    ctx: WorkspaceContext = Depends(_admin_gate),
    session: AsyncSession = Depends(get_async_session),
):
    if data.provider not in ("focus_nfe", "enotas", "plugnotas"):
        raise HTTPException(status_code=422, detail="Provedor inválido")
    if data.environment not in ("homologation", "production"):
        raise HTTPException(status_code=422, detail="Ambiente inválido")
    try:
        config = await fiscal_emission_service.save_provider_config(
            session,
            workspace_id,
            provider=data.provider,
            api_key=data.api_key,
            environment=data.environment,
            cnpj_emitente=data.cnpj_emitente,
            serie_padrao=data.serie_padrao,
        )
        await session.commit()
    except FiscalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return FiscalProviderConfigRead(
        workspace_id=config.workspace_id,
        provider=config.provider,
        environment=config.environment,
        cnpj_emitente=config.cnpj_emitente,
        serie_padrao=config.serie_padrao,
        has_api_key=True,
        updated_at=config.updated_at,
    )


# ────────────────────────────────────────────────────────────────────────────
# Listagem de emissões
# ────────────────────────────────────────────────────────────────────────────

@router.get("/api/workspaces/{workspace_id}/fiscal/emissions", response_model=list[FiscalEmissionRead])
async def list_fiscal_emissions(
    workspace_id: uuid.UUID,
    invoice_id: uuid.UUID | None = None,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    rows = await fiscal_emission_service.list_emissions(session, workspace_id, invoice_id=invoice_id)
    return [_to_read(r) for r in rows]


# ────────────────────────────────────────────────────────────────────────────
# Emitir NF-e para uma fatura
# ────────────────────────────────────────────────────────────────────────────

@router.post(
    "/api/workspaces/{workspace_id}/invoices/{invoice_id}/emit-nfe",
    response_model=FiscalEmissionRead,
    status_code=201,
)
async def emit_nfe(
    workspace_id: uuid.UUID,
    invoice_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_emit_gate),
    session: AsyncSession = Depends(get_async_session),
):
    invoice = await get_invoice(session, invoice_id, workspace_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    try:
        emission = await fiscal_emission_service.emit_nfe(session, workspace_id, invoice)
    except FiscalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _to_read(emission)


# ────────────────────────────────────────────────────────────────────────────
# Refresh de status
# ────────────────────────────────────────────────────────────────────────────

@router.post(
    "/api/workspaces/{workspace_id}/fiscal/emissions/{emission_id}/refresh",
    response_model=FiscalEmissionRead,
)
async def refresh_emission(
    workspace_id: uuid.UUID,
    emission_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_emit_gate),
    session: AsyncSession = Depends(get_async_session),
):
    emission = await fiscal_emission_service.get_emission(session, emission_id, workspace_id)
    if not emission:
        raise HTTPException(status_code=404, detail="Emissão não encontrada")
    try:
        emission = await fiscal_emission_service.refresh_emission(session, emission)
    except FiscalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _to_read(emission)


# ────────────────────────────────────────────────────────────────────────────
# Cancelamento
# ────────────────────────────────────────────────────────────────────────────

@router.post(
    "/api/workspaces/{workspace_id}/fiscal/emissions/{emission_id}/cancel",
    response_model=FiscalEmissionRead,
)
async def cancel_emission(
    workspace_id: uuid.UUID,
    emission_id: uuid.UUID,
    data: CancelEmissionRequest,
    ctx: WorkspaceContext = Depends(_emit_gate),
    session: AsyncSession = Depends(get_async_session),
):
    emission = await fiscal_emission_service.get_emission(session, emission_id, workspace_id)
    if not emission:
        raise HTTPException(status_code=404, detail="Emissão não encontrada")
    try:
        emission = await fiscal_emission_service.cancel_emission(session, emission, data.justificativa)
    except FiscalError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return _to_read(emission)


# ────────────────────────────────────────────────────────────────────────────
# Callback do provedor (webhook de retorno)
# ────────────────────────────────────────────────────────────────────────────

@router.post("/api/fiscal/callback/{provider}", status_code=200)
async def fiscal_callback(
    provider: str,
    request: Request,
):
    """Ponto de entrada para callbacks assíncronos do provedor.

    O Focus NFe chama este endpoint quando o status de uma NF-e muda
    (ex.: autorizada, denegada). Por ora apenas loga o payload; a
    implementação completa requer ligar o provider_ref ao FiscalEmission
    e chamar refresh_emission automaticamente.

    Sem autenticação de workspace: o provedor não conhece o workspace,
    apenas a referência. A validação real deve ser por HMAC ou token
    por provedor (implementação futura).
    """
    body = await request.body()
    logger.info("fiscal callback provider=%s payload=%s", provider, body[:500])
    return {"ok": True}


# ────────────────────────────────────────────────────────────────────────────
# Helper
# ────────────────────────────────────────────────────────────────────────────

def _to_read(e: "FiscalEmission") -> FiscalEmissionRead:  # type: ignore[name-defined]
    from app.models.fiscal_emission import FiscalEmission as _FE  # noqa: F401
    return FiscalEmissionRead(
        id=e.id,
        workspace_id=e.workspace_id,
        invoice_id=e.invoice_id,
        provider=e.provider,
        environment=e.environment,
        status=e.status,
        provider_ref=e.provider_ref,
        chave_acesso=e.chave_acesso,
        nfe_number=e.nfe_number,
        nfe_serie=e.nfe_serie,
        xml_url=e.xml_url,
        pdf_url=e.pdf_url,
        error_message=e.error_message,
        error_code=e.error_code,
        created_at=e.created_at,
        updated_at=e.updated_at,
    )
