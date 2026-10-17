"""document retention fields on invoice_attachments (B6)

Revision ID: 117
Revises: 116
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision: str = "117"
down_revision: str = "116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoice_attachments",
        sa.Column("is_locked", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "invoice_attachments",
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "invoice_attachments",
        sa.Column("locked_by", sa.String(50), nullable=True),
    )
    op.add_column(
        "invoice_attachments",
        sa.Column("retention_until", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoice_attachments", "retention_until")
    op.drop_column("invoice_attachments", "locked_by")
    op.drop_column("invoice_attachments", "locked_at")
    op.drop_column("invoice_attachments", "is_locked")
