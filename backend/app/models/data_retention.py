import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DataRetentionPolicy(Base):
    """Workspace-level data retention configuration (D2).

    Controls how long financial data, attachments and audit events are kept
    before automatic anonymization or disposal.
    """

    __tablename__ = "data_retention_policies"
    __table_args__ = (
        CheckConstraint("transaction_retention_days >= 365", name="ck_retention_transaction_min"),
        CheckConstraint("attachment_retention_days >= 365", name="ck_retention_attachment_min"),
        CheckConstraint("audit_retention_days >= 365", name="ck_retention_audit_min"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, index=True
    )
    transaction_retention_days: Mapped[int] = mapped_column(
        Integer, default=2555, server_default="2555"
    )
    attachment_retention_days: Mapped[int] = mapped_column(
        Integer, default=1825, server_default="1825"
    )
    audit_retention_days: Mapped[int] = mapped_column(
        Integer, default=3650, server_default="3650"
    )
    anonymize_on_expiry: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    last_purge_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=lambda: datetime.now(timezone.utc)
    )
