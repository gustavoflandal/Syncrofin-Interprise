"""in-app notifications

Revision ID: 091
Revises: 090
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "091"
down_revision: Union[str, None] = "090"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False, server_default="info"),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("dedupe_key", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_notification_user_dedupe"),
    )
    op.create_index("ix_notifications_workspace_id", "notifications", ["workspace_id"])
    op.create_index(
        "ix_notifications_inbox",
        "notifications",
        ["user_id", "workspace_id", "read_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_inbox", table_name="notifications")
    op.drop_index("ix_notifications_workspace_id", table_name="notifications")
    op.drop_table("notifications")
