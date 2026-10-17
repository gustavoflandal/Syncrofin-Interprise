"""Ordens de pagamento PIX/TED com dupla aprovação obrigatória (F4).

Regras que valem para toda ordem, sem opção de desligar:

  - quem cria não aprova;
  - o segundo aprovador é diferente do criador e do primeiro;
  - quem envia ao provedor não é o criador nem nenhum dos dois aprovadores.

Dinheiro sai daqui, então as transições de estado são feitas com a linha
travada (`FOR UPDATE`): dois cliques simultâneos em "Enviar" não podem chamar o
provedor duas vezes. A chave de idempotência da ordem também vai ao provedor.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment_order import (
    ACCOUNT_TYPES,
    PAYMENT_METHODS,
    PIX_KEY_TYPES,
    TERMINAL_PAYMENT_STATUSES,
    PaymentApprovalEvent,
    PaymentOrder,
)
from app.providers.payment_provider import PaymentProvider, PaymentRequest, PaymentResult
from app.providers.sandbox_payment import SandboxPaymentProvider

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = "sandbox"

# Campos que o criador pode informar/editar enquanto a ordem é rascunho.
_EDITABLE_FIELDS = (
    "method", "amount", "currency", "description", "beneficiary_name", "beneficiary_tax_id",
    "pix_key", "pix_key_type", "bank_code", "branch", "account_number", "account_type",
    "source_account_id", "invoice_id", "payee_id", "provider",
)


def get_provider(name: str) -> PaymentProvider:
    """Adaptadores registrados. Os reais (Inter, Cora, ...) entram aqui."""
    if name == "sandbox":
        return SandboxPaymentProvider()
    raise HTTPException(status_code=400, detail=f"Provedor de pagamento desconhecido: {name!r}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

async def get_order(
    session: AsyncSession, order_id: uuid.UUID, workspace_id: uuid.UUID, *, lock: bool = False
) -> PaymentOrder:
    q = select(PaymentOrder).where(PaymentOrder.id == order_id, PaymentOrder.workspace_id == workspace_id)
    if lock:
        q = q.with_for_update()
    order = (await session.execute(q)).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Ordem de pagamento não encontrada")
    return order


async def list_orders(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[PaymentOrder], int]:
    base = select(PaymentOrder).where(PaymentOrder.workspace_id == workspace_id)
    if status:
        base = base.where(PaymentOrder.status == status)
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        await session.execute(
            base.order_by(PaymentOrder.created_at.desc(), PaymentOrder.id)
            .offset(max(page - 1, 0) * limit)
            .limit(limit)
        )
    ).scalars().all()
    return list(rows), total


async def list_events(
    session: AsyncSession, order_id: uuid.UUID, workspace_id: uuid.UUID
) -> list[PaymentApprovalEvent]:
    rows = await session.execute(
        select(PaymentApprovalEvent)
        .where(
            PaymentApprovalEvent.payment_order_id == order_id,
            PaymentApprovalEvent.workspace_id == workspace_id,
        )
        .order_by(PaymentApprovalEvent.created_at, PaymentApprovalEvent.id)
    )
    return list(rows.scalars().all())


def _log(session: AsyncSession, order: PaymentOrder, user_id: uuid.UUID, action: str, note: Optional[str] = None):
    session.add(
        PaymentApprovalEvent(
            id=uuid.uuid4(),
            payment_order_id=order.id,
            workspace_id=order.workspace_id,
            user_id=user_id,
            action=action,
            note=note,
        )
    )


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------

def _validate_payload(o: PaymentOrder) -> None:
    """Coerência do método com os dados do favorecido."""
    if o.method not in PAYMENT_METHODS:
        raise HTTPException(status_code=422, detail="Método deve ser 'pix' ou 'ted'")
    if o.amount is None or Decimal(o.amount) <= 0:
        raise HTTPException(status_code=422, detail="O valor deve ser maior que zero")
    if o.method == "pix":
        if not o.pix_key:
            raise HTTPException(status_code=422, detail="PIX exige a chave PIX")
        if o.pix_key_type not in PIX_KEY_TYPES:
            raise HTTPException(status_code=422, detail="Tipo de chave PIX inválido")
    else:
        if not (o.bank_code and o.branch and o.account_number):
            raise HTTPException(status_code=422, detail="TED exige banco, agência e conta")
        if o.account_type not in ACCOUNT_TYPES:
            raise HTTPException(status_code=422, detail="Tipo de conta deve ser 'checking' ou 'savings'")


async def _check_references(session: AsyncSession, o: PaymentOrder) -> None:
    """Conta, fatura e favorecido citados precisam ser do mesmo workspace."""
    from app.models.account import Account
    from app.models.invoice import Invoice
    from app.models.payee import Payee

    for model, value, label in (
        (Account, o.source_account_id, "Conta de origem"),
        (Invoice, o.invoice_id, "Fatura"),
        (Payee, o.payee_id, "Favorecido"),
    ):
        if value is None:
            continue
        found = (
            await session.execute(
                select(model.id).where(model.id == value, model.workspace_id == o.workspace_id)
            )
        ).scalar_one_or_none()
        if found is None:
            raise HTTPException(status_code=422, detail=f"{label} não pertence a este workspace")


# ---------------------------------------------------------------------------
# Ciclo de vida
# ---------------------------------------------------------------------------

async def create_order(
    session: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID, data: dict[str, Any]
) -> tuple[PaymentOrder, bool]:
    """Cria um rascunho. Devolve `(ordem, criada)`.

    Repetir a mesma `idempotency_key` devolve a ordem já existente (`criada=False`)
    em vez de duplicar o pagamento — é o que torna seguro um cliente reenviar.
    """
    key = data.get("idempotency_key") or str(uuid.uuid4())
    existing = (
        await session.execute(
            select(PaymentOrder).where(
                PaymentOrder.workspace_id == workspace_id, PaymentOrder.idempotency_key == key
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    fields = {k: data[k] for k in _EDITABLE_FIELDS if k in data and data[k] is not None}
    order = PaymentOrder(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        idempotency_key=key,
        created_by_user_id=user_id,
        status="draft",
        approval_status="none",
        currency="BRL",
        **fields,
    )
    order.provider = order.provider or DEFAULT_PROVIDER
    get_provider(order.provider)  # falha cedo se o provedor não existe
    _validate_payload(order)
    await _check_references(session, order)
    session.add(order)
    try:
        await session.flush()
    except IntegrityError:
        # Corrida com outra requisição de mesma chave: vence a primeira.
        await session.rollback()
        winner = (
            await session.execute(
                select(PaymentOrder).where(
                    PaymentOrder.workspace_id == workspace_id, PaymentOrder.idempotency_key == key
                )
            )
        ).scalar_one_or_none()
        if winner is None:
            raise
        return winner, False
    return order, True


async def update_order(
    session: AsyncSession, order_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID, data: dict[str, Any]
) -> PaymentOrder:
    order = await get_order(session, order_id, workspace_id, lock=True)
    if order.status != "draft":
        raise HTTPException(status_code=409, detail="Só é possível editar ordens em rascunho")
    for k in _EDITABLE_FIELDS:
        if k in data:
            setattr(order, k, data[k])
    _validate_payload(order)
    await _check_references(session, order)
    await session.flush()
    return order


async def submit_for_approval(
    session: AsyncSession, order_id: uuid.UUID, user_id: uuid.UUID, workspace_id: Optional[uuid.UUID] = None
) -> PaymentOrder:
    order = await _locked(session, order_id, workspace_id)
    if order.status != "draft":
        raise HTTPException(status_code=409, detail="Só ordens em rascunho podem ser enviadas para aprovação")
    _validate_payload(order)
    order.status = "pending_approval"
    order.approval_status = "pending"
    _log(session, order, user_id, "submit")
    await session.flush()
    return order


async def approve(
    session: AsyncSession, order_id: uuid.UUID, user_id: uuid.UUID,
    workspace_id: Optional[uuid.UUID] = None, note: Optional[str] = None,
) -> PaymentOrder:
    order = await _locked(session, order_id, workspace_id)
    if order.status != "pending_approval":
        raise HTTPException(status_code=409, detail="A ordem não está aguardando aprovação")
    if user_id == order.created_by_user_id:
        raise HTTPException(status_code=403, detail="Quem criou a ordem não pode aprová-la")
    if order.first_approver_id is None:
        order.first_approver_id = user_id
        order.first_approved_at = _now()
    else:
        if user_id == order.first_approver_id:
            raise HTTPException(status_code=403, detail="A segunda aprovação deve ser de outra pessoa")
        order.second_approver_id = user_id
        order.second_approved_at = _now()
        order.status = "approved"
        order.approval_status = "approved"
    _log(session, order, user_id, "approve", note)
    await session.flush()
    return order


async def reject(
    session: AsyncSession, order_id: uuid.UUID, user_id: uuid.UUID,
    note: Optional[str] = None, workspace_id: Optional[uuid.UUID] = None,
) -> PaymentOrder:
    order = await _locked(session, order_id, workspace_id)
    if order.status != "pending_approval":
        raise HTTPException(status_code=409, detail="A ordem não está aguardando aprovação")
    if user_id == order.created_by_user_id:
        raise HTTPException(status_code=403, detail="Quem criou a ordem não pode rejeitá-la; use cancelar")
    # Volta a rascunho e zera as aprovações já dadas: o criador precisa reenviar.
    order.status = "draft"
    order.approval_status = "none"
    order.first_approver_id = order.first_approved_at = None
    order.second_approver_id = order.second_approved_at = None
    _log(session, order, user_id, "reject", note)
    await session.flush()
    return order


async def send_payment(
    session: AsyncSession, order_id: uuid.UUID, user_id: uuid.UUID, workspace_id: Optional[uuid.UUID] = None
) -> PaymentOrder:
    order = await _locked(session, order_id, workspace_id)
    if order.status != "approved":
        raise HTTPException(status_code=409, detail="Só ordens aprovadas podem ser enviadas")
    if order.first_approver_id is None or order.second_approver_id is None:
        raise HTTPException(status_code=409, detail="A ordem não tem as duas aprovações")
    if user_id in (order.created_by_user_id, order.first_approver_id, order.second_approver_id):
        raise HTTPException(
            status_code=403, detail="Quem envia deve ser diferente de quem criou e de quem aprovou"
        )
    provider = get_provider(order.provider or DEFAULT_PROVIDER)
    request = PaymentRequest(
        idempotency_key=order.idempotency_key,
        amount=Decimal(order.amount),
        currency=order.currency,
        method=order.method,
        pix_key=order.pix_key,
        pix_key_type=order.pix_key_type,
        bank_code=order.bank_code,
        branch=order.branch,
        account_number=order.account_number,
        account_type=order.account_type,
        beneficiary_name=order.beneficiary_name,
        beneficiary_tax_id=order.beneficiary_tax_id,
        description=order.description or "",
    )
    try:
        result = await provider.create_payment(request)
    except Exception as exc:  # o provedor pode ter recebido; a idempotência cobre o reenvio
        logger.exception("payment provider error order=%s", order.id)
        order.provider_error = str(exc)[:1000]
        await session.flush()
        raise HTTPException(status_code=502, detail="Erro ao enviar ao provedor de pagamento") from exc

    order.sent_by_user_id = user_id
    order.sent_at = _now()
    order.external_id = result.external_id
    _log(session, order, user_id, "send")
    await _apply_result(session, order, result, initial=True)
    await session.flush()
    return order


async def check_status(
    session: AsyncSession, order_id: uuid.UUID, workspace_id: Optional[uuid.UUID] = None
) -> PaymentOrder:
    order = await _locked(session, order_id, workspace_id)
    if order.status != "sent" or not order.external_id:
        return order
    provider = get_provider(order.provider or DEFAULT_PROVIDER)
    try:
        result = await provider.get_status(order.external_id)
    except Exception as exc:
        logger.exception("payment status check failed order=%s", order.id)
        raise HTTPException(status_code=502, detail="Erro ao consultar o provedor de pagamento") from exc
    await _apply_result(session, order, result)
    await session.flush()
    return order


async def cancel(
    session: AsyncSession, order_id: uuid.UUID, user_id: uuid.UUID, workspace_id: Optional[uuid.UUID] = None
) -> PaymentOrder:
    order = await _locked(session, order_id, workspace_id)
    if order.status in TERMINAL_PAYMENT_STATUSES:
        raise HTTPException(status_code=409, detail="A ordem já foi finalizada")
    if order.status == "sent":
        # Já está no provedor: só cancela se ele aceitar.
        provider = get_provider(order.provider or DEFAULT_PROVIDER)
        try:
            result = await provider.cancel_payment(order.external_id or "")
        except Exception as exc:
            raise HTTPException(status_code=502, detail="Erro ao cancelar no provedor de pagamento") from exc
        if result.status != "cancelled":
            raise HTTPException(status_code=409, detail="O provedor não aceitou o cancelamento")
    order.status = "cancelled"
    order.approval_status = "none" if order.approval_status != "approved" else order.approval_status
    _log(session, order, user_id, "cancel")
    await session.flush()
    return order


async def handle_webhook(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    provider_name: str,
    payload: dict,
    headers: Optional[dict] = None,
    raw_body: bytes = b"",
) -> Optional[PaymentOrder]:
    """Processa o retorno do provedor. Devolve a ordem, ou None se não for nossa."""
    provider = get_provider(provider_name)
    if not await provider.verify_webhook(headers or {}, raw_body):
        raise HTTPException(status_code=401, detail="Webhook inválido")
    event = await provider.parse_webhook_event(payload)
    if not event.external_id:
        return None
    order = (
        await session.execute(
            select(PaymentOrder)
            .where(
                PaymentOrder.workspace_id == workspace_id,
                PaymentOrder.provider == provider_name,
                PaymentOrder.external_id == event.external_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if order is None or order.status != "sent":
        return order
    if event.status == "confirmed":
        # Nunca baixa dinheiro só pela palavra do webhook: confirma consultando o provedor.
        event = await provider.get_status(event.external_id)
    await _apply_result(session, order, event)
    await session.flush()
    return order


# ---------------------------------------------------------------------------
# Internos
# ---------------------------------------------------------------------------

async def _locked(session: AsyncSession, order_id: uuid.UUID, workspace_id: Optional[uuid.UUID]) -> PaymentOrder:
    if workspace_id is None:
        ws = (
            await session.execute(select(PaymentOrder.workspace_id).where(PaymentOrder.id == order_id))
        ).scalar_one_or_none()
        if ws is None:
            raise HTTPException(status_code=404, detail="Ordem de pagamento não encontrada")
        workspace_id = ws
    return await get_order(session, order_id, workspace_id, lock=True)


async def _apply_result(
    session: AsyncSession, order: PaymentOrder, result: PaymentResult, initial: bool = False
) -> None:
    """Traduz o estado do provedor para o da ordem."""
    if result.receipt_url:
        order.receipt_url = result.receipt_url[:500]
    if result.status == "confirmed":
        order.status = "confirmed"
        order.confirmed_at = result.completed_at or _now()
        order.provider_error = None
        await _create_transaction(session, order)
    elif result.status == "failed":
        order.status = "failed"
        order.provider_error = result.error or "Pagamento recusado pelo provedor"
    elif result.status == "cancelled":
        order.status = "cancelled"
    else:  # pending | processing
        order.status = "sent"
        if initial:
            order.provider_error = None


async def _create_transaction(session: AsyncSession, order: PaymentOrder) -> None:
    """Lança a despesa quando o pagamento é confirmado. Idempotente."""
    if order.transaction_id is not None:
        return
    from app.models.account import Account
    from app.models.invoice import Invoice, InvoiceAllocation
    from app.models.transaction import Transaction

    account_id = order.source_account_id
    if account_id is None:
        account_id = (
            await session.execute(
                select(Account.id)
                .where(
                    Account.workspace_id == order.workspace_id,
                    Account.type == "checking",
                    Account.is_closed.is_(False),
                )
                .order_by(Account.name, Account.id)
                .limit(1)
            )
        ).scalar_one_or_none()
    if account_id is None:
        logger.warning("payment %s confirmed but no account to post the transaction", order.id)
        return

    tx_date = (order.confirmed_at or _now()).date()
    tx = Transaction(
        id=uuid.uuid4(),
        workspace_id=order.workspace_id,
        account_id=account_id,
        user_id=order.created_by_user_id,
        date=tx_date,
        effective_date=tx_date,
        description=(f"{order.method.upper()} - {order.beneficiary_name}")[:500],
        amount=order.amount,
        currency=order.currency,
        type="debit",
        status="posted",
        source="payment",
        payee_id=order.payee_id,
    )
    session.add(tx)
    await session.flush()
    order.transaction_id = tx.id

    if order.invoice_id is not None:
        invoice = await session.get(Invoice, order.invoice_id)
        if invoice is not None and invoice.workspace_id == order.workspace_id:
            session.add(
                InvoiceAllocation(
                    id=uuid.uuid4(),
                    invoice_id=invoice.id,
                    transaction_id=tx.id,
                    amount=order.amount,
                    workspace_id=order.workspace_id,
                    method="payment_order",
                )
            )


async def poll_sent_orders(session: AsyncSession) -> int:
    """Consulta o provedor para toda ordem 'sent' (usado pela tarefa periódica)."""
    ids = (
        await session.execute(
            select(PaymentOrder.id, PaymentOrder.workspace_id).where(PaymentOrder.status == "sent")
        )
    ).all()
    changed = 0
    for oid, wid in ids:
        try:
            order = await check_status(session, oid, wid)
            await session.commit()
            if order.status != "sent":
                changed += 1
        except Exception:
            await session.rollback()
            logger.exception("payment poll failed order=%s", oid)
    return changed
