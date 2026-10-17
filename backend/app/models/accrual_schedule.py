import uuid
from datetime import date as _date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.transaction import Transaction


class AccrualSchedule(Base):
    """Cronograma de provisão (despesa reconhecida mês a mês) ou diferimento (receita)."""

    __tablename__ = "accrual_schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    source_transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str] = mapped_column(String(500))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2))
    type: Mapped[str] = mapped_column(String(20))  # accrual | deferral
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    cost_center_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cost_centers.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    start_date: Mapped[_date] = mapped_column(Date)
    end_date: Mapped[_date] = mapped_column(Date)
    period_count: Mapped[int] = mapped_column(Integer)
    amount_per_period: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2))
    currency: Mapped[str] = mapped_column(String(3), default="BRL")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    entries: Mapped[list["AccrualEntry"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan", order_by="AccrualEntry.period_date"
    )


class AccrualEntry(Base):
    __tablename__ = "accrual_entries"
    __table_args__ = (
        UniqueConstraint("schedule_id", "period_date", name="uq_accrual_entry_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accrual_schedules.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    period_date: Mapped[_date] = mapped_column(Date)  # primeiro dia do mês
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2))
    transaction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    schedule: Mapped["AccrualSchedule"] = relationship(back_populates="entries")
    transaction: Mapped[Optional["Transaction"]] = relationship()
