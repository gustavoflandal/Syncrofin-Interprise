"""data retention policy (D2)

Revision ID: 119
Revises: 118
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "119"
down_revision: str = "118"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_retention_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("transaction_retention_days", sa.Integer(), nullable=False, server_default="2555"),
        sa.Column("attachment_retention_days", sa.Integer(), nullable=False, server_default="1825"),
        sa.Column("audit_retention_days", sa.Integer(), nullable=False, server_default="3650"),
        sa.Column("anonymize_on_expiry", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_purge_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("transaction_retention_days >= 365", name="ck_retention_transaction_min"),
        sa.CheckConstraint("attachment_retention_days >= 365", name="ck_retention_attachment_min"),
        sa.CheckConstraint("audit_retention_days >= 365", name="ck_retention_audit_min"),
    )
    op.create_index("ix_data_retention_policies_workspace", "data_retention_policies", ["workspace_id"], unique=True)


def downgrade() -> None:
    op.drop_table("data_retention_policies")
