"""API de cobrança por boleto e PIX (B2).

Rotas:
  GET/PUT /api/workspaces/{id}/billing/provider-config
  GET     /api/workspaces/{id}/billing/charges
  GET     /api/workspaces/{id}/invoices/{inv_id}/billing/charges
  POST    /api/workspaces/{id}/invoices/{inv_id}/billing/charges
  POST    /api/workspaces/{id}/billing/charges/{charge_id}/refresh
  POST    /api/workspaces/{id}/billing/charges/{charge_id}/cancel
  POST    /api/billing/webhook/{provider}/{workspace_id}  (sem auth — verificação por token)
"""
import uuid
import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, require_permission
from app.models.billing_charge import BillingCharge
from app.services import billing_service
from app.services.billing_service import (
    BillingChargeError,
    BillingConfigNotFoundError,
)
from app.services.invoice_service import get_invoice
from app.providers.billing_provider import ChargeRequest

logger = logging.getLogger(__name__)

_billing_gate = require_permission("billing.manage")
_read_gate = require_permission("billing.read")

router = APIRouter(tags=["billing"])


# ────────────────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────────────────

class BillingProviderConfigRead(BaseModel):
    provider: str
    environment: str
    webhook_token: str
    has_api_key: bool
    updated_at: str

    model_config = {"from_attributes": True}


class BillingProviderConfigSave(BaseModel):
    provider: str
    api_key: str
    environment: str = "sandbox"


class BillingChargeRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    invoice_id: uuid.UUID
    provider: str
    environment: str
    method: str
    external_id: Optional[str]
    status: str
    amount: Decimal
    due_date: date
    boleto_url: Optional[str]
    boleto_line: Optional[str]
    pix_copy_paste: Optional[str]
    pix_qrcode: Optional[str]
    paid_at: Optional[str]
    paid_amount: Optional[Decimal]
    transaction_id: Optional[uuid.UUID]
    error_message: Optional[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class CreateChargeRequest(BaseModel):
    provider: str = "asaas"
    method: str  # 'boleto' | 'pix'
    amount: Decimal
    due_date: date
    payer_name: str
    payer_cpf_cnpj: str
    payer_email: Optional[str] = None
    payer_phone: Optional[str] = None
    description: str = ""
    # Endereço (obrigatório para boleto)
    payer_address: str = ""
    payer_address_number: str = ""
    payer_complement: str = ""
    payer_neighborhood: str = ""
    payer_city: str = ""
    payer_state: str = ""
    payer_zip: str = ""


# ────────────────────────────────────────────────────────────────────────────
# Configuração do provedor
# ────────────────────────────────────────────────────────────────────────────

@router.get("/api/workspaces/{workspace_id}/billing/provider-config")
async def get_billing_config(
    workspace_id: uuid.UUID,
    provider: str = "asaas",
    ctx: WorkspaceContext = Depends(require_permission("billing.manage")),
    session: AsyncSession = Depends(get_async_session),
):
    cfg = await billing_service.get_provider_config(session, workspace_id, provider)
    if not cfg:
        raise HTTPException(status_code=404, detail="Provedor de cobrança não configurado")
    return BillingProviderConfigRead(
        provider=cfg.provider,
        environment=cfg.environment,
        webhook_token=cfg.webhook_token,
        has_api_key=bool(cfg.api_key_enc),
        updated_at=cfg.updated_at.isoformat(),
    )


@router.put("/api/workspaces/{workspace_id}/billing/provider-config", status_code=200)
async def save_billing_config(
    workspace_id: uuid.UUID,
    body: BillingProviderConfigSave,
    ctx: WorkspaceContext = Depends(require_permission("billing.manage")),
    session: AsyncSession = Depends(get_async_session),
):
    cfg = await billing_service.save_provider_config(
        session, workspace_id, body.provider, body.api_key, body.environment
    )
    await session.commit()
    return BillingProviderConfigRead(
        provider=cfg.provider,
        environment=cfg.environment,
        webhook_token=cfg.webhook_token,
        has_api_key=True,
        updated_at=cfg.updated_at.isoformat(),
    )


# ────────────────────────────────────────────────────────────────────────────
# Cobranças
# ────────────────────────────────────────────────────────────────────────────

@router.get("/api/workspaces/{workspace_id}/billing/charges", response_model=list[BillingChargeRead])
async def list_all_charges(
    workspace_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_permission("billing.read")),
    session: AsyncSession = Depends(get_async_session),
):
    return await billing_service.list_charges(session, workspace_id)


@router.get(
    "/api/workspaces/{workspace_id}/invoices/{invoice_id}/billing/charges",
    response_model=list[BillingChargeRead],
)
async def list_invoice_charges(
    workspace_id: uuid.UUID,
    invoice_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_permission("billing.read")),
    session: AsyncSession = Depends(get_async_session),
):
    return await billing_service.list_charges(session, workspace_id, invoice_id)


@router.post(
    "/api/workspaces/{workspace_id}/invoices/{invoice_id}/billing/charges",
    response_model=BillingChargeRead,
    status_code=201,
)
async def create_charge(
    workspace_id: uuid.UUID,
    invoice_id: uuid.UUID,
    body: CreateChargeRequest,
    ctx: WorkspaceContext = Depends(require_permission("billing.manage")),
    session: AsyncSession = Depends(get_async_session),
):
    invoice = await get_invoice(session, invoice_id, workspace_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura não encontrada")
    req = ChargeRequest(
        method=body.method,
        amount=body.amount,
        due_date=body.due_date,
        payer_name=body.payer_name,
        payer_cpf_cnpj=body.payer_cpf_cnpj,
        payer_email=body.payer_email,
        payer_phone=body.payer_phone,
        description=body.description or (invoice.number or ""),
        reference=invoice.number or str(invoice_id),
        payer_address=body.payer_address,
        payer_address_number=body.payer_address_number,
        payer_complement=body.payer_complement,
        payer_neighborhood=body.payer_neighborhood,
        payer_city=body.payer_city,
        payer_state=body.payer_state,
        payer_zip=body.payer_zip,
    )
    try:
        charge = await billing_service.create_charge(
            session, workspace_id, invoice_id, body.provider, req
        )
    except BillingConfigNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except BillingChargeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await session.commit()
    await session.refresh(charge)
    return charge


@router.post(
    "/api/workspaces/{workspace_id}/billing/charges/{charge_id}/refresh",
    response_model=BillingChargeRead,
)
async def refresh_charge(
    workspace_id: uuid.UUID,
    charge_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_permission("billing.manage")),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(BillingCharge).where(
            BillingCharge.id == charge_id,
            BillingCharge.workspace_id == workspace_id,
        )
    )
    charge = result.scalar_one_or_none()
    if not charge:
        raise HTTPException(status_code=404, detail="Cobrança não encontrada")
    try:
        await billing_service.refresh_charge(session, charge)
    except (BillingConfigNotFoundError, BillingChargeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await session.commit()
    return charge


@router.post(
    "/api/workspaces/{workspace_id}/billing/charges/{charge_id}/cancel",
    response_model=BillingChargeRead,
)
async def cancel_charge(
    workspace_id: uuid.UUID,
    charge_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(require_permission("billing.manage")),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(BillingCharge).where(
            BillingCharge.id == charge_id,
            BillingCharge.workspace_id == workspace_id,
        )
    )
    charge = result.scalar_one_or_none()
    if not charge:
        raise HTTPException(status_code=404, detail="Cobrança não encontrada")
    try:
        await billing_service.cancel_charge(session, charge)
    except (BillingConfigNotFoundError, BillingChargeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await session.commit()
    return charge


# ────────────────────────────────────────────────────────────────────────────
# Webhook (público — verificação por token no header)
# ────────────────────────────────────────────────────────────────────────────

@router.post(
    "/api/billing/webhook/{provider}/{workspace_id}",
    status_code=200,
    include_in_schema=False,
)
async def billing_webhook(
    provider: str,
    workspace_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Receive payment confirmation from the billing provider.

    Asaas sends the API key in the `access_token` header.  We match it against
    the `webhook_token` we store (which is a random hex we generated, not the
    Asaas API key — the caller passed our token when registering the webhook on
    Asaas, so verify_webhook compares them).
    """
    token = request.headers.get("access_token", "")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    try:
        await billing_service.apply_webhook_event(session, workspace_id, provider, token, payload)
    except BillingChargeError as exc:
        logger.warning("billing webhook rejected: %s", exc)
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception:
        logger.exception("billing webhook error workspace=%s provider=%s", workspace_id, provider)
        raise HTTPException(status_code=500, detail="Internal error")
    await session.commit()
    return {"received": True}
