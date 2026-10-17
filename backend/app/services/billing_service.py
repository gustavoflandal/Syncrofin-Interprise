"""Serviço de cobrança por boleto/PIX (B2).

Fluxo principal:
  1. `save_provider_config`  — salva credenciais do provedor (criptografadas)
  2. `create_charge`         — cria cobrança no provedor e persiste BillingCharge
  3. `refresh_charge`        — consulta status atualizado e atualiza localmente
  4. `cancel_charge`         — cancela no provedor e marca local como 'cancelled'
  5. `apply_webhook_event`   — processa notificação de pagamento e baixa a fatura
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value, encrypt_value
from app.models.billing_charge import (
    BillingCharge,
    BillingProviderConfig,
    TERMINAL_BILLING_STATUSES,
)
from app.models.invoice import Invoice
from app.models.workspace import Workspace
from app.providers.billing_provider import ChargeRequest, ChargeStatus
from app.providers.asaas_billing import AsaasBillingProvider


class BillingConfigNotFoundError(Exception):
    pass


class BillingChargeError(Exception):
    pass


def _get_provider(name: str):
    if name == "asaas":
        return AsaasBillingProvider()
    raise ValueError(f"Provedor de cobrança desconhecido: {name!r}")


async def get_provider_config(
    session: AsyncSession, workspace_id: uuid.UUID, provider: str
) -> Optional[BillingProviderConfig]:
    result = await session.execute(
        select(BillingProviderConfig).where(
            BillingProviderConfig.workspace_id == workspace_id,
            BillingProviderConfig.provider == provider,
        )
    )
    return result.scalar_one_or_none()


async def save_provider_config(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    provider: str,
    api_key: str,
    environment: str = "sandbox",
) -> BillingProviderConfig:
    existing = await get_provider_config(session, workspace_id, provider)
    if existing:
        existing.api_key_enc = encrypt_value(api_key)
        existing.environment = environment
        existing.updated_at = datetime.now(timezone.utc)
        return existing
    cfg = BillingProviderConfig(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        provider=provider,
        environment=environment,
        api_key_enc=encrypt_value(api_key),
        webhook_token=secrets.token_hex(32),
    )
    session.add(cfg)
    return cfg


async def list_charges(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    invoice_id: Optional[uuid.UUID] = None,
) -> list[BillingCharge]:
    q = select(BillingCharge).where(BillingCharge.workspace_id == workspace_id)
    if invoice_id is not None:
        q = q.where(BillingCharge.invoice_id == invoice_id)
    result = await session.execute(q.order_by(BillingCharge.created_at.desc()))
    return list(result.scalars().all())


async def create_charge(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    invoice_id: uuid.UUID,
    provider_name: str,
    req: ChargeRequest,
) -> BillingCharge:
    cfg = await get_provider_config(session, workspace_id, provider_name)
    if cfg is None:
        raise BillingConfigNotFoundError(
            f"Configure as credenciais do provedor '{provider_name}' antes de emitir cobranças."
        )
    api_key = decrypt_value(cfg.api_key_enc)
    provider = _get_provider(provider_name)
    try:
        result = await provider.create_charge(req, api_key, cfg.environment)
    except Exception as exc:
        raise BillingChargeError(f"Erro ao criar cobrança no provedor: {exc}") from exc

    charge = BillingCharge(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        invoice_id=invoice_id,
        provider=provider_name,
        environment=cfg.environment,
        method=req.method,
        external_id=result.external_id,
        status=result.status,
        amount=req.amount,
        due_date=req.due_date,
        boleto_url=result.boleto_url,
        boleto_barcode=result.boleto_barcode,
        boleto_line=result.boleto_line,
        pix_qrcode=result.pix_qrcode,
        pix_copy_paste=result.pix_copy_paste,
    )
    session.add(charge)
    return charge


async def refresh_charge(
    session: AsyncSession,
    charge: BillingCharge,
) -> BillingCharge:
    if charge.status in TERMINAL_BILLING_STATUSES:
        return charge
    cfg = await get_provider_config(session, charge.workspace_id, charge.provider)
    if cfg is None:
        raise BillingConfigNotFoundError("Configuração do provedor não encontrada.")
    api_key = decrypt_value(cfg.api_key_enc)
    provider = _get_provider(charge.provider)
    status_data: ChargeStatus = await provider.get_charge_status(
        charge.external_id, api_key, cfg.environment
    )
    _apply_status(charge, status_data)
    return charge


async def cancel_charge(
    session: AsyncSession,
    charge: BillingCharge,
) -> BillingCharge:
    if charge.status in TERMINAL_BILLING_STATUSES:
        raise BillingChargeError(
            f"Não é possível cancelar cobrança com status '{charge.status}'."
        )
    cfg = await get_provider_config(session, charge.workspace_id, charge.provider)
    if cfg is None:
        raise BillingConfigNotFoundError("Configuração do provedor não encontrada.")
    api_key = decrypt_value(cfg.api_key_enc)
    provider = _get_provider(charge.provider)
    await provider.cancel_charge(charge.external_id, api_key, cfg.environment)
    charge.status = "cancelled"
    charge.updated_at = datetime.now(timezone.utc)
    return charge


async def apply_webhook_event(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    provider_name: str,
    webhook_token: str,
    payload: dict,
) -> Optional[BillingCharge]:
    """Process an incoming webhook event from the billing provider.

    Returns the updated BillingCharge when found, or None when the external_id
    doesn't match any known charge (safe to ignore — may be from another workspace).
    """
    cfg = await get_provider_config(session, workspace_id, provider_name)
    if cfg is None:
        return None
    provider = _get_provider(provider_name)
    if not provider.verify_webhook(webhook_token, cfg.webhook_token):
        raise BillingChargeError("Webhook token inválido.")

    status_data = provider.parse_webhook_event(payload)
    result = await session.execute(
        select(BillingCharge).where(
            BillingCharge.workspace_id == workspace_id,
            BillingCharge.external_id == status_data.external_id,
        )
    )
    charge = result.scalar_one_or_none()
    if charge is None:
        return None
    _apply_status(charge, status_data)
    # Auto-settle the invoice when payment is confirmed/received
    if charge.status in ("confirmed", "received") and charge.paid_amount:
        await _auto_settle(session, charge)
    return charge


async def _auto_settle(session: AsyncSession, charge: BillingCharge) -> None:
    """Record a transaction that settles the invoice when payment arrives."""
    from app.models.invoice import InvoiceAllocation
    from app.models.transaction import Transaction

    invoice = await session.get(Invoice, charge.invoice_id)
    if invoice is None:
        return
    workspace = await session.get(Workspace, charge.workspace_id)
    if workspace is None:
        return

    # Find or create a default settlement account (first checking account)
    from app.models.account import Account
    from sqlalchemy import select
    account_result = await session.execute(
        select(Account).where(
            Account.workspace_id == charge.workspace_id,
            Account.type == "checking",
            Account.is_closed.is_(False),
        ).limit(1)
    )
    account = account_result.scalar_one_or_none()
    if account is None:
        return  # cannot auto-settle without a known bank account

    paid_amount = charge.paid_amount or charge.amount
    tx_date = charge.paid_at.date() if charge.paid_at else datetime.now(timezone.utc).date()
    tx = Transaction(
        id=uuid.uuid4(),
        workspace_id=charge.workspace_id,
        account_id=account.id,
        user_id=invoice.user_id,
        date=tx_date,
        effective_date=tx_date,
        description=f"Pagamento automático — cobrança {charge.external_id[:12]}",
        amount=paid_amount,
        currency=invoice.currency,
        type="credit" if invoice.direction == "receivable" else "debit",
        status="posted",
        source="manual",
    )
    session.add(tx)

    alloc = InvoiceAllocation(
        id=uuid.uuid4(),
        invoice_id=charge.invoice_id,
        transaction_id=tx.id,
        amount=paid_amount,
        workspace_id=charge.workspace_id,
        method="billing_webhook",
    )
    session.add(alloc)
    charge.transaction_id = tx.id


def _apply_status(charge: BillingCharge, status_data: ChargeStatus) -> None:
    charge.status = status_data.status
    charge.updated_at = datetime.now(timezone.utc)
    if status_data.paid_at:
        try:
            charge.paid_at = datetime.fromisoformat(status_data.paid_at.replace("Z", "+00:00"))
        except ValueError:
            pass
    if status_data.paid_amount is not None:
        charge.paid_amount = status_data.paid_amount
