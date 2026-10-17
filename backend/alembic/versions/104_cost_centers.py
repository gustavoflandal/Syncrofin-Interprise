"""cost_centers: new entity + cost_center_id FK on transactions and budgets

Revision ID: 104
Revises: 103
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "104"
down_revision: Union[str, None] = "103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cost_centers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("code", sa.String(20), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "transactions",
        sa.Column("cost_center_id", UUID(as_uuid=True), sa.ForeignKey("cost_centers.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column(
        "budgets",
        sa.Column("cost_center_id", UUID(as_uuid=True), sa.ForeignKey("cost_centers.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_transactions_cost_center_id", "transactions", ["cost_center_id"])
    op.create_index("ix_budgets_cost_center_id", "budgets", ["cost_center_id"])


def downgrade() -> None:
    op.drop_index("ix_budgets_cost_center_id", table_name="budgets")
    op.drop_index("ix_transactions_cost_center_id", table_name="transactions")
    op.drop_column("budgets", "cost_center_id")
    op.drop_column("transactions", "cost_center_id")
    op.drop_table("cost_centers")
