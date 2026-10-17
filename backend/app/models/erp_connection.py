"""Conexões com ERPs externos (F3): credenciais, mapeamento de entidades e histórico de sincronização.

`erp_entity_mappings` é o que torna a sincronização idempotente: liga o id local ao id do ERP por
(conexão, tipo de entidade). Rodar o mesmo pull duas vezes atualiza em vez de duplicar.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SUPPORTED_ERP_PROVIDERS = frozenset({"omie", "contaazul"})
ENTITY_TYPES = frozenset({"category", "payee", "transaction", "invoice"})


class ErpConnection(Base):
    __tablename__ = "erp_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    # Quem criou: dono das categorias/beneficiários importados (esses modelos exigem `user_id`).
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(50))  # "omie" | "contaazul"
    # JSON cifrado (Fernet). Nunca devolvido pela API.
    credentials_enc: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_sync_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sync_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )


class ErpEntityMapping(Base):
    __tablename__ = "erp_entity_mappings"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "entity_type", "external_id", name="uq_erp_mapping_external"
        ),
        UniqueConstraint("connection_id", "entity_type", "local_id", name="uq_erp_mapping_local"),
        Index("ix_erp_mapping_lookup", "connection_id", "entity_type", "external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_connections.id", ondelete="CASCADE")
    )
    entity_type: Mapped[str] = mapped_column(String(50))  # category | payee | transaction | invoice
    local_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    external_id: Mapped[str] = mapped_column(String(255))


class ErpSyncRun(Base):
    __tablename__ = "erp_sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("erp_connections.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|success|error
    entity_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    direction: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # pull | push
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[Any]] = mapped_column(JSONB, default=list)
