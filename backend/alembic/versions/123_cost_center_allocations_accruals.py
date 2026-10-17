"""rateio entre centros de custo e provisões/diferimentos (A8)

Revision ID: 123
Revises: 122
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "123"
down_revision: str = "122"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cost_center_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cost_center_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cost_centers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("percentage", sa.Numeric(7, 4), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("transaction_id", "cost_center_id", name="uq_cc_allocation"),
        sa.CheckConstraint("amount <> 0", name="ck_cc_allocation_nonzero"),
    )
    op.create_index("ix_cost_center_allocations_workspace_id", "cost_center_allocations", ["workspace_id"])
    op.create_index("ix_cost_center_allocations_transaction_id", "cost_center_allocations", ["transaction_id"])
    op.create_index("ix_cost_center_allocations_cost_center_id", "cost_center_allocations", ["cost_center_id"])

    op.create_table(
        "accrual_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_transaction_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("total_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cost_center_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cost_centers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("period_count", sa.Integer, nullable=False),
        sa.Column("amount_per_period", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="BRL"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_accrual_schedules_workspace_id", "accrual_schedules", ["workspace_id"])

    op.create_table(
        "accrual_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("accrual_schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_date", sa.Date, nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("schedule_id", "period_date", name="uq_accrual_entry_period"),
    )
    op.create_index("ix_accrual_entries_schedule_id", "accrual_entries", ["schedule_id"])
    op.create_index("ix_accrual_entries_workspace_id", "accrual_entries", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("accrual_entries")
    op.drop_table("accrual_schedules")
    op.drop_table("cost_center_allocations")
