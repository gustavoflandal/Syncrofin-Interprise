"""workspace mfa_required flag (C5)

Revision ID: 113
Revises: 112
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa

revision: str = "113"
down_revision: str = "112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("mfa_required", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "mfa_required")
