"""sessions: what makes a login revocable

Revision ID: 094
Revises: 093
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "094"
down_revision: Union[str, None] = "093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_hash", sa.String(64), nullable=False),
        sa.Column("previous_refresh_hash", sa.String(64), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(40), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("device_label", sa.String(120), nullable=True),
        sa.Column("auth_method", sa.String(20), nullable=False),
    )
    op.create_index("ix_user_sessions_refresh_hash", "user_sessions", ["refresh_hash"], unique=True)
    op.create_index("ix_user_sessions_previous_refresh_hash", "user_sessions", ["previous_refresh_hash"])
    op.create_index("ix_user_sessions_user_active", "user_sessions", ["user_id", "revoked_at"])


def downgrade() -> None:
    op.drop_table("user_sessions")
