"""outbound webhook endpoints and delivery log (F2)

Revision ID: 110
Revises: 109
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "110"
down_revision: str = "109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secret", sa.Text, nullable=True),
        sa.Column(
            "events",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "endpoint_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("http_status", sa.Integer, nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
