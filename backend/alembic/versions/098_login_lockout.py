"""Lock an account after repeated wrong passwords

Revision ID: 098
Revises: 097
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "098"
down_revision: Union[str, None] = "097"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("lock_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("last_failed_login_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for column in ("locked_until", "last_failed_login_at", "lock_count", "failed_login_count"):
        op.drop_column("users", column)
