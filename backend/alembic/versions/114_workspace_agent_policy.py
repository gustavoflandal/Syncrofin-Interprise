"""workspace: agents_enabled + agent_data_policy (D6)

Revision ID: 114
Revises: 113
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "114"
down_revision: str = "113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspaces",
        sa.Column("agents_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "workspaces",
        sa.Column("agent_data_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "agent_data_policy")
    op.drop_column("workspaces", "agents_enabled")
