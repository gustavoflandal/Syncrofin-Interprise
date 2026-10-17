from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, String, ForeignKey, UniqueConstraint, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class PeriodClose(Base):
    __tablename__ = "period_closes"
    __table_args__ = (
        UniqueConstraint("workspace_id", "year", "month", name="uq_period_closes_workspace_year_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    closed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    reopened_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reopened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reopen_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
