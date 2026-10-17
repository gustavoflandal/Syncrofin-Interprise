"""chart_of_accounts: add parent_id, code, natureza, depth to category_groups

Revision ID: 103
Revises: 102
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "103"
down_revision: Union[str, None] = "102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "category_groups",
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("category_groups.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("category_groups", sa.Column("code", sa.String(20), nullable=True))
    op.add_column("category_groups", sa.Column("natureza", sa.String(20), nullable=True))
    op.add_column(
        "category_groups",
        sa.Column("depth", sa.SmallInteger(), nullable=False, server_default="0"),
    )
    op.create_index("ix_category_groups_parent_id", "category_groups", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_category_groups_parent_id", table_name="category_groups")
    op.drop_column("category_groups", "depth")
    op.drop_column("category_groups", "natureza")
    op.drop_column("category_groups", "code")
    op.drop_column("category_groups", "parent_id")
