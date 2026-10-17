import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.invoice import Invoice


class InvoiceWithholding(Base):
    __tablename__ = "invoice_withholdings"
    __table_args__ = (
        UniqueConstraint("invoice_id", "tax_type", name="uq_withholding_per_type"),
        CheckConstraint(
            "tax_type IN ('irrf', 'iss', 'pis', 'cofins', 'csll', 'inss', 'other')",
            name="ck_withholding_tax_type",
        ),
        CheckConstraint("withheld_amount > 0", name="ck_withholding_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    tax_type: Mapped[str] = mapped_column(String(20))
    rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(precision=7, scale=4), nullable=True)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2))
    withheld_amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped["Invoice"] = relationship(back_populates="withholdings")
