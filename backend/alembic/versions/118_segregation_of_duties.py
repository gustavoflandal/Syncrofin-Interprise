"""segregation of duties: settlement tracking + workspace flag (C3)

Revision ID: 118
Revises: 117
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "118"
down_revision: str = "117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Settlement tracking on transactions
    op.add_column(
        "transactions",
        sa.Column(
            "settled_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "transactions",
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Workspace-level segregation toggle
    op.add_column(
        "workspaces",
        sa.Column(
            "segregation_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "segregation_enabled")
    op.drop_column("transactions", "settled_at")
    op.drop_column("transactions", "settled_by_user_id")
