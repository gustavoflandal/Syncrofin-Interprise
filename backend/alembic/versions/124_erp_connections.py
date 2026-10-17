"""conexões ERP, mapeamento de entidades e execuções de sync (F3)

Revision ID: 124
Revises: 123
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "124"
down_revision: str = "123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erp_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("credentials_enc", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(20), nullable=True),
        sa.Column("last_sync_error", sa.Text, nullable=True),
        sa.Column(
            "sync_config", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "erp_entity_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("local_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.UniqueConstraint(
            "connection_id", "entity_type", "external_id", name="uq_erp_mapping_external"
        ),
        sa.UniqueConstraint(
            "connection_id", "entity_type", "local_id", name="uq_erp_mapping_local"
        ),
    )
    op.create_index(
        "ix_erp_mapping_lookup",
        "erp_entity_mappings",
        ["connection_id", "entity_type", "external_id"],
    )

    op.create_table(
        "erp_sync_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("direction", sa.String(10), nullable=True),
        sa.Column("created_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "errors", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
    )


def downgrade() -> None:
    op.drop_table("erp_sync_runs")
    op.drop_index("ix_erp_mapping_lookup", table_name="erp_entity_mappings")
    op.drop_table("erp_entity_mappings")
    op.drop_table("erp_connections")
