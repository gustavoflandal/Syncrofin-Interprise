"""Modelos de cobrança por boleto e PIX (B2).

Dois registros por workspace:
  - BillingProviderConfig  — credenciais do provedor (1 por provider)
  - BillingCharge          — cada cobrança emitida ligada a uma fatura
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SUPPORTED_BILLING_PROVIDERS = frozenset({"asaas", "inter", "cora", "pagbrasil"})
BILLING_METHODS = frozenset({"boleto", "pix", "credit_card"})
BILLING_STATUSES = frozenset({
    "pending",
    "awaiting_payment",
    "received",
    "confirmed",
    "overdue",
    "cancelled",
    "error",
})
TERMINAL_BILLING_STATUSES = frozenset({"received", "confirmed", "cancelled", "error"})


class BillingProviderConfig(Base):
    __tablename__ = "billing_provider_configs"
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider", name="uq_bpc_workspace_provider"),
        CheckConstraint("environment IN ('sandbox', 'production')", name="ck_bpc_environment"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    environment: Mapped[str] = mapped_column(String(20), nullable=False, default="sandbox")
    api_key_enc: Mapped[str] = mapped_column(Text(), nullable=False)
    webhook_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class BillingCharge(Base):
    __tablename__ = "billing_charges"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'awaiting_payment', 'received', 'confirmed', 'overdue', 'cancelled', 'error')",
            name="ck_bc_status",
        ),
        CheckConstraint("method IN ('boleto', 'pix', 'credit_card')", name="ck_bc_method"),
        Index("ix_billing_charges_workspace", "workspace_id"),
        Index("ix_billing_charges_workspace_invoice", "workspace_id", "invoice_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    due_date: Mapped[date] = mapped_column(Date(), nullable=False)
    # Boleto
    boleto_url: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    boleto_barcode: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    boleto_line: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # PIX
    pix_qrcode: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    pix_copy_paste: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    # Settlement
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="SET NULL"),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
