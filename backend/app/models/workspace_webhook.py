"""Webhooks de saída configurados por workspace.

Cada workspace pode ter vários endpoints. Quando um evento de negócio
ocorre (transação criada, fatura paga, etc.), `webhook_service.dispatch`
envia um POST assíncrono para todos os webhooks ativos do workspace que
subscrevem aquele evento, com assinatura HMAC-SHA256 no cabeçalho
`X-SyncroFin-Signature` quando um segredo estiver configurado.

Tipos de evento atualmente suportados:
  transaction.created  transaction.updated  transaction.deleted
  invoice.created      invoice.paid         invoice.void
  reconciliation.applied
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

#: Conjunto fechado de tipos de evento reconhecidos.
#: Novos tipos chegam como constantes aqui; o banco guarda strings livres,
#: mas a API valida contra este conjunto.
EVENT_TYPES = frozenset(
    {
        "transaction.created",
        "transaction.updated",
        "transaction.deleted",
        "invoice.created",
        "invoice.paid",
        "invoice.void",
        "reconciliation.applied",
    }
)


class WorkspaceWebhook(Base):
    __tablename__ = "workspace_webhooks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    url: Mapped[str] = mapped_column(String(2048))
    # Plain text; the API accepts it on create/update and never returns it.
    secret: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    # NULL = subscribe to all events; list = subscribe to listed events only.
    event_types: Mapped[Optional[list[Any]]] = mapped_column(JSON, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_fired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
