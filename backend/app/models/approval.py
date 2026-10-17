from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional
from decimal import Decimal
from sqlalchemy import DateTime, String, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class WorkspaceApprovalRule(Base):
    __tablename__ = "workspace_approval_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    # null = regra global; preenchido = regra específica para esse grupo
    category_group_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("category_groups.id", ondelete="CASCADE"), nullable=True
    )
    amount_threshold: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL", server_default="BRL")
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ApprovalEvent(Base):
    __tablename__ = "approval_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # submitted | approved | rejected | cancelled
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
