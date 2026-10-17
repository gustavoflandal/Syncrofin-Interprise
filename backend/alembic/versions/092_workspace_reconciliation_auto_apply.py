"""letting a workspace accept confident reconciliation suggestions on its own

Revision ID: 092
Revises: 091
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "092"
down_revision: Union[str, None] = "091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Null = off, which is what every existing workspace keeps.
    op.add_column(
        "workspaces",
        sa.Column("reconciliation_auto_apply_score", sa.Numeric(3, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "reconciliation_auto_apply_score")
