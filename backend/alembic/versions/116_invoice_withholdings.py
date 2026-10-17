"""invoice_withholdings table for tax withholdings on invoices (B3/T6)

Revision ID: 116
Revises: 115
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "116"
down_revision: str = "115"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_withholdings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tax_type", sa.String(20), nullable=False),
        sa.Column("rate", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("base_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("withheld_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("invoice_id", "tax_type", name="uq_withholding_per_type"),
        sa.CheckConstraint(
            "tax_type IN ('irrf', 'iss', 'pis', 'cofins', 'csll', 'inss', 'other')",
            name="ck_withholding_tax_type",
        ),
        sa.CheckConstraint("withheld_amount > 0", name="ck_withholding_positive"),
    )
    op.create_index("ix_invoice_withholdings_invoice", "invoice_withholdings", ["invoice_id"])
    op.create_index("ix_invoice_withholdings_workspace", "invoice_withholdings", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_invoice_withholdings_workspace", table_name="invoice_withholdings")
    op.drop_index("ix_invoice_withholdings_invoice", table_name="invoice_withholdings")
    op.drop_table("invoice_withholdings")
