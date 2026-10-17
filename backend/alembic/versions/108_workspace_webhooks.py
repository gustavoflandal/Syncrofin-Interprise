"""workspace_webhooks — webhooks de saída por workspace (F2)

Revision ID: 108
Revises: 107
Create Date: 2026-10-06
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "108"
down_revision: str = "107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_webhooks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        # HMAC-SHA256 signing secret; null means no signature header is sent.
        sa.Column("secret", sa.String(256), nullable=True),
        # JSON array of event type strings, e.g. ["transaction.created", "invoice.paid"].
        # NULL or empty means "all events".
        sa.Column("event_types", sa.JSON, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Updated on each delivery attempt.
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_code", sa.Integer, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("workspace_webhooks")
