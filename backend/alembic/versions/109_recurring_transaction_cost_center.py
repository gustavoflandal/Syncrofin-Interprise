"""recurring_transaction_cost_center: add cost_center_id to recurring_transactions

Revision ID: 109
Revises: 108
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "109"
down_revision: Union[str, None] = "108"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recurring_transactions",
        sa.Column(
            "cost_center_id",
            UUID(as_uuid=True),
            sa.ForeignKey("cost_centers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_recurring_transactions_cost_center_id",
        "recurring_transactions",
        ["cost_center_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_recurring_transactions_cost_center_id", table_name="recurring_transactions")
    op.drop_column("recurring_transactions", "cost_center_id")
