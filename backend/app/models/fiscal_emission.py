"""Modelos de emissão fiscal (B1).

Dois registros por workspace:
  - FiscalProviderConfig  — credenciais do provedor (1 por workspace)
  - FiscalEmission        — cada tentativa de emissão ligada a uma fatura

A chave de API é armazenada criptografada com a mesma infra do TOTP
(app.core.crypto). Nunca é devolvida em texto pela API.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Provedores suportados. Lista fechada para evitar referências fantasma em
# código que despacha pelo nome do provedor.
SUPPORTED_PROVIDERS = frozenset({"focus_nfe", "enotas", "plugnotas"})

# Estados de emissão. Transitions:
#  pending → processing → issued
#                       → error
#  issued  → cancelled
EMISSION_STATUSES = frozenset({"pending", "processing", "issued", "cancelled", "error"})


class FiscalProviderConfig(Base):
    """Credenciais do provedor de NF-e de um workspace.

    Um workspace tem no máximo uma configuração ativa; a constraint UNIQUE
    impede o drift que ocorre quando código de migração esquece de deletar
    a antiga antes de criar a nova.
    """

    __tablename__ = "fiscal_provider_configs"
    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_fiscal_provider_config_workspace"),
        CheckConstraint(
            "provider IN ('focus_nfe', 'enotas', 'plugnotas')",
            name="ck_fiscal_provider",
        ),
        CheckConstraint(
            "environment IN ('homologation', 'production')",
            name="ck_fiscal_provider_env",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )

    provider: Mapped[str] = mapped_column(String(30))
    environment: Mapped[str] = mapped_column(
        String(20), default="homologation", server_default="homologation"
    )
    # API key criptografada com app.core.crypto. Nunca exposta diretamente.
    api_key_encrypted: Mapped[str] = mapped_column(Text)
    # CNPJ do emitente no formato de 14 dígitos sem máscara
    cnpj_emitente: Mapped[Optional[str]] = mapped_column(String(14), nullable=True)
    # Série padrão para NF-e (tipicamente "1" para produção)
    serie_padrao: Mapped[str] = mapped_column(String(5), default="1", server_default="1")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class FiscalEmission(Base):
    """Uma tentativa de emissão de NF-e ligada a uma fatura."""

    __tablename__ = "fiscal_emissions"
    __table_args__ = (
        Index("ix_fiscal_emissions_workspace_invoice", "workspace_id", "invoice_id"),
        Index("ix_fiscal_emissions_workspace_status", "workspace_id", "status"),
        CheckConstraint(
            "provider IN ('focus_nfe', 'enotas', 'plugnotas')",
            name="ck_fe_provider",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'issued', 'cancelled', 'error')",
            name="ck_fe_status",
        ),
        CheckConstraint(
            "environment IN ('homologation', 'production')",
            name="ck_fe_environment",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )

    provider: Mapped[str] = mapped_column(String(30))
    environment: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", index=True)

    # Referência gerada pelo SyncroFin ao chamar o provedor (uuid como string)
    provider_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Chave de acesso NF-e (44 dígitos) — preenchida quando issued
    chave_acesso: Mapped[Optional[str]] = mapped_column(String(44), nullable=True, index=True)
    # Número e série da NF-e — preenchidos quando issued
    nfe_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    nfe_serie: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    # URL do XML e do PDF devolvidos pelo provedor
    xml_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pdf_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Mensagem de erro do provedor (para status='error')
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
