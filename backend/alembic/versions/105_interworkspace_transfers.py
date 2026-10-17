"""add is_cross_workspace_transfer to transactions

Revision ID: 105
Revises: 104
Create Date: 2026-10-05

A9 — cross-workspace PF/PJ transfers.
The flag lets get_transfer_pair and delete_transaction skip the
workspace_id filter when resolving the counterpart transaction.
"""

from alembic import op
import sqlalchemy as sa

revision = "105"
down_revision = "104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column(
            "is_cross_workspace_transfer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("transactions", "is_cross_workspace_transfer")
