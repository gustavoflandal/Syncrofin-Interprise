"""Ordens de pagamento (F4): iniciação de PIX/TED pela API bancária com dupla aprovação.

Duas tabelas:
  - PaymentOrder          — a ordem, com a trilha de aprovadores e o rastreio no provedor
  - PaymentApprovalEvent  — trilha de auditoria (aprovou, rejeitou, enviou, cancelou)

Ciclo de vida: draft -> pending_approval -> approved -> sent -> confirmed | failed | cancelled.
A dupla aprovação é sempre exigida: não existe configuração para desligá-la.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

PAYMENT_METHODS = frozenset({"pix", "ted"})
PIX_KEY_TYPES = frozenset({"cpf", "cnpj", "email", "phone", "random"})
ACCOUNT_TYPES = frozenset({"checking", "savings"})
PAYMENT_STATUSES = frozenset(
    {"draft", "pending_approval", "approved", "sent", "confirmed", "failed", "cancelled"}
)
#: Estados dos quais a ordem não sai mais.
TERMINAL_PAYMENT_STATUSES = frozenset({"confirmed", "failed", "cancelled"})


def _user_fk(nullable: bool = True) -> Mapped:
    return mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=nullable)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    __table_args__ = (
        UniqueConstraint("workspace_id", "idempotency_key", name="uq_payment_order_idempotency"),
        CheckConstraint("amount > 0", name="ck_payment_order_positive"),
        Index("ix_payment_orders_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)

    # Pagamento
    method: Mapped[str] = mapped_column(String(10), nullable=False)  # pix | ted
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL", server_default="BRL")
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Favorecido
    beneficiary_name: Mapped[str] = mapped_column(String(255), nullable=False)
    beneficiary_tax_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    pix_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pix_key_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    bank_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    branch: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    account_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    account_type: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Origem
    source_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    invoice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True
    )
    payee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payees.id", ondelete="SET NULL"), nullable=True
    )

    # Estado e aprovação
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    # none -> pending -> approved (exige dois aprovadores distintos)
    approval_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none", server_default="none"
    )

    created_by_user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    first_approver_id: Mapped[Optional[uuid.UUID]] = _user_fk()
    first_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    second_approver_id: Mapped[Optional[uuid.UUID]] = _user_fk()
    second_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_by_user_id: Mapped[Optional[uuid.UUID]] = _user_fk()
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Rastreio no provedor
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    provider_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    receipt_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Lançamento gerado na confirmação
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PaymentApprovalEvent(Base):
    __tablename__ = "payment_approval_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    # submit | approve | reject | send | cancel
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
