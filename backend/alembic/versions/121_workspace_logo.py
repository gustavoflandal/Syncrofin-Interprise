"""workspace logo storage key (G2)

Revision ID: 121
Revises: 120
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision: str = "121"
down_revision: str = "120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("logo_storage_key", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "logo_storage_key")
