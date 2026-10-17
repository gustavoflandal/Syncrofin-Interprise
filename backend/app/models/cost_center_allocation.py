import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.cost_center import CostCenter
    from app.models.transaction import Transaction


class CostCenterAllocation(Base):
    """Uma fatia do rateio (A8) de uma transação entre centros de custo.

    Regra: se a transação tem alocações, elas somam exatamente `transaction.amount`;
    sem alocações vale o `transaction.cost_center_id` único (compatível com o legado).
    """

    __tablename__ = "cost_center_allocations"
    __table_args__ = (
        UniqueConstraint("transaction_id", "cost_center_id", name="uq_cc_allocation"),
        CheckConstraint("amount <> 0", name="ck_cc_allocation_nonzero"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    cost_center_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cost_centers.id", ondelete="RESTRICT"), index=True
    )
    # Mesma escala de Transaction.amount (2 casas): a soma das fatias fecha no centavo.
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=15, scale=2))
    percentage: Mapped[Optional[Decimal]] = mapped_column(Numeric(precision=7, scale=4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    transaction: Mapped["Transaction"] = relationship(back_populates="cost_center_allocations")
    # joined: o nome do centro vai junto na leitura da transação (evita lazy load no async).
    cost_center: Mapped["CostCenter"] = relationship(lazy="joined")

    @property
    def cost_center_name(self) -> Optional[str]:
        return self.cost_center.name if self.cost_center else None
