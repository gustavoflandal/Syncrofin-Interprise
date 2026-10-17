"""period close and approval flow (A5/A6)

Revision ID: 106
Revises: 105
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "106"
down_revision: str = "105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "period_closes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("closed_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("reopened_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reopened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reopen_reason", sa.String(500), nullable=True),
        sa.UniqueConstraint("workspace_id", "year", "month",
                            name="uq_period_closes_workspace_year_month"),
    )

    op.create_table(
        "workspace_approval_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("category_group_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("category_groups.id", ondelete="CASCADE"), nullable=True),
        sa.Column("amount_threshold", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="BRL"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_table(
        "approval_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.add_column("transactions",
        sa.Column("approval_status", sa.String(20), nullable=True))
    op.create_index("ix_transactions_approval_status", "transactions", ["approval_status"])

    op.add_column("workspaces",
        sa.Column("period_close_by", sa.String(20), nullable=False, server_default="date"))
    op.add_column("workspaces",
        sa.Column("period_close_sync_mode", sa.String(20), nullable=False, server_default="reject"))


def downgrade() -> None:
    op.drop_column("workspaces", "period_close_sync_mode")
    op.drop_column("workspaces", "period_close_by")
    op.drop_index("ix_transactions_approval_status", table_name="transactions")
    op.drop_column("transactions", "approval_status")
    op.drop_table("approval_events")
    op.drop_table("workspace_approval_rules")
    op.drop_table("period_closes")
