"""API de ordens de pagamento PIX/TED com dupla aprovação (F4).

Permissões: `payments.read` (GET), `payments.write` (criar, editar, cancelar),
`payments.approve` (aprovar/rejeitar), `payments.send` (enviar ao provedor).
A segregação de funções é regra do serviço e vale para qualquer papel.
"""
import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, require_permission
from app.services import payment_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])

_read = require_permission("payments.read")
_write = require_permission("payments.write")
_approve = require_permission("payments.approve")
_send = require_permission("payments.send")


class PaymentOrderBase(BaseModel):
    method: Literal["pix", "ted"]
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    currency: str = Field(default="BRL", min_length=3, max_length=3)
    description: Optional[str] = Field(default=None, max_length=500)
    beneficiary_name: str = Field(min_length=1, max_length=255)
    beneficiary_tax_id: Optional[str] = Field(default=None, max_length=20)
    pix_key: Optional[str] = Field(default=None, max_length=255)
    pix_key_type: Optional[Literal["cpf", "cnpj", "email", "phone", "random"]] = None
    bank_code: Optional[str] = Field(default=None, max_length=10)
    branch: Optional[str] = Field(default=None, max_length=10)
    account_number: Optional[str] = Field(default=None, max_length=20)
    account_type: Optional[Literal["checking", "savings"]] = None
    source_account_id: Optional[uuid.UUID] = None
    invoice_id: Optional[uuid.UUID] = None
    payee_id: Optional[uuid.UUID] = None
    provider: str = Field(default="sandbox", max_length=50)


class PaymentOrderCreate(PaymentOrderBase):
    idempotency_key: Optional[str] = Field(default=None, min_length=1, max_length=100)


class PaymentOrderUpdate(BaseModel):
    method: Optional[Literal["pix", "ted"]] = None
    amount: Optional[Decimal] = Field(default=None, gt=0, max_digits=15, decimal_places=2)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    description: Optional[str] = Field(default=None, max_length=500)
    beneficiary_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    beneficiary_tax_id: Optional[str] = Field(default=None, max_length=20)
    pix_key: Optional[str] = Field(default=None, max_length=255)
    pix_key_type: Optional[Literal["cpf", "cnpj", "email", "phone", "random"]] = None
    bank_code: Optional[str] = Field(default=None, max_length=10)
    branch: Optional[str] = Field(default=None, max_length=10)
    account_number: Optional[str] = Field(default=None, max_length=20)
    account_type: Optional[Literal["checking", "savings"]] = None
    source_account_id: Optional[uuid.UUID] = None
    invoice_id: Optional[uuid.UUID] = None
    payee_id: Optional[uuid.UUID] = None


class NoteBody(BaseModel):
    note: Optional[str] = Field(default=None, max_length=1000)


class PaymentOrderRead(PaymentOrderBase):
    id: uuid.UUID
    workspace_id: uuid.UUID
    idempotency_key: str
    status: str
    approval_status: str
    created_by_user_id: uuid.UUID
    first_approver_id: Optional[uuid.UUID] = None
    first_approved_at: Optional[datetime] = None
    second_approver_id: Optional[uuid.UUID] = None
    second_approved_at: Optional[datetime] = None
    sent_by_user_id: Optional[uuid.UUID] = None
    sent_at: Optional[datetime] = None
    provider: Optional[str] = None
    external_id: Optional[str] = None
    provider_error: Optional[str] = None
    receipt_url: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    transaction_id: Optional[uuid.UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaymentEventRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    action: str
    note: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaymentOrderDetail(PaymentOrderRead):
    events: list[PaymentEventRead] = []


class PaymentOrderPage(BaseModel):
    items: list[PaymentOrderRead]
    total: int
    page: int
    limit: int


async def _detail(session: AsyncSession, order) -> PaymentOrderDetail:
    events = await payment_service.list_events(session, order.id, order.workspace_id)
    out = PaymentOrderDetail.model_validate(order)
    out.events = [PaymentEventRead.model_validate(e) for e in events]
    return out


@router.get("", response_model=PaymentOrderPage)
async def list_payments(
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    ctx: WorkspaceContext = Depends(_read),
    session: AsyncSession = Depends(get_async_session),
):
    items, total = await payment_service.list_orders(session, ctx.workspace.id, status, page, limit)
    return PaymentOrderPage(
        items=[PaymentOrderRead.model_validate(o) for o in items], total=total, page=page, limit=limit
    )


@router.post("", response_model=PaymentOrderDetail, status_code=201)
async def create_payment(
    body: PaymentOrderCreate,
    ctx: WorkspaceContext = Depends(_write),
    session: AsyncSession = Depends(get_async_session),
):
    order, created = await payment_service.create_order(
        session, ctx.workspace.id, ctx.user_id, body.model_dump(exclude_unset=True)
    )
    if created:
        await session.commit()
    else:
        # Mesma chave de idempotência: devolve a ordem existente sem tocar nela.
        await session.rollback()
    return await _detail(session, order)


@router.get("/{order_id}", response_model=PaymentOrderDetail)
async def get_payment(
    order_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_read),
    session: AsyncSession = Depends(get_async_session),
):
    order = await payment_service.get_order(session, order_id, ctx.workspace.id)
    return await _detail(session, order)


@router.patch("/{order_id}", response_model=PaymentOrderDetail)
async def update_payment(
    order_id: uuid.UUID,
    body: PaymentOrderUpdate,
    ctx: WorkspaceContext = Depends(_write),
    session: AsyncSession = Depends(get_async_session),
):
    order = await payment_service.update_order(
        session, order_id, ctx.workspace.id, ctx.user_id, body.model_dump(exclude_unset=True)
    )
    await session.commit()
    return await _detail(session, order)


@router.delete("/{order_id}", response_model=PaymentOrderDetail)
async def cancel_payment(
    order_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_write),
    session: AsyncSession = Depends(get_async_session),
):
    order = await payment_service.cancel(session, order_id, ctx.user_id, ctx.workspace.id)
    await session.commit()
    return await _detail(session, order)


@router.post("/{order_id}/submit", response_model=PaymentOrderDetail)
async def submit_payment(
    order_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_write),
    session: AsyncSession = Depends(get_async_session),
):
    order = await payment_service.submit_for_approval(session, order_id, ctx.user_id, ctx.workspace.id)
    await session.commit()
    return await _detail(session, order)


@router.post("/{order_id}/approve", response_model=PaymentOrderDetail)
async def approve_payment(
    order_id: uuid.UUID,
    body: NoteBody = NoteBody(),
    ctx: WorkspaceContext = Depends(_approve),
    session: AsyncSession = Depends(get_async_session),
):
    order = await payment_service.approve(session, order_id, ctx.user_id, ctx.workspace.id, body.note)
    await session.commit()
    return await _detail(session, order)


@router.post("/{order_id}/reject", response_model=PaymentOrderDetail)
async def reject_payment(
    order_id: uuid.UUID,
    body: NoteBody = NoteBody(),
    ctx: WorkspaceContext = Depends(_approve),
    session: AsyncSession = Depends(get_async_session),
):
    order = await payment_service.reject(session, order_id, ctx.user_id, body.note, ctx.workspace.id)
    await session.commit()
    return await _detail(session, order)


@router.post("/{order_id}/send", response_model=PaymentOrderDetail)
async def send_payment(
    order_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_send),
    session: AsyncSession = Depends(get_async_session),
):
    order = await payment_service.send_payment(session, order_id, ctx.user_id, ctx.workspace.id)
    await session.commit()
    return await _detail(session, order)


@router.post("/{order_id}/check", response_model=PaymentOrderDetail)
async def check_payment(
    order_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_write),
    session: AsyncSession = Depends(get_async_session),
):
    order = await payment_service.check_status(session, order_id, ctx.workspace.id)
    await session.commit()
    return await _detail(session, order)


@router.post("/webhook/{provider}/{workspace_id}", status_code=200, include_in_schema=False)
async def payment_webhook(
    provider: str,
    workspace_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Retorno do provedor; sem sessão de usuário, a autenticidade é do `verify_webhook`."""
    raw = await request.body()
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON")
    await payment_service.handle_webhook(
        session, workspace_id, provider, payload, dict(request.headers), raw
    )
    await session.commit()
    return {"received": True}
