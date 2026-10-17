"""cobrança por boleto e PIX (B2)

Revision ID: 112
Revises: 111
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "112"
down_revision: str = "111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Provider config (Asaas API key per workspace)
    op.create_table(
        "billing_provider_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False, server_default="sandbox"),
        sa.Column("api_key_enc", sa.Text(), nullable=False),
        sa.Column("webhook_token", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "provider", name="uq_bpc_workspace_provider"),
        sa.CheckConstraint(
            "environment IN ('sandbox', 'production')",
            name="ck_bpc_environment",
        ),
    )

    # Individual charge linked to an Invoice
    op.create_table(
        "billing_charges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),  # 'boleto' | 'pix' | 'credit_card'
        sa.Column("external_id", sa.String(100), nullable=True, index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        # Boleto
        sa.Column("boleto_url", sa.Text(), nullable=True),
        sa.Column("boleto_barcode", sa.Text(), nullable=True),
        sa.Column("boleto_line", sa.String(200), nullable=True),
        # PIX
        sa.Column("pix_qrcode", sa.Text(), nullable=True),
        sa.Column("pix_copy_paste", sa.Text(), nullable=True),
        # Settlement
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('pending', 'awaiting_payment', 'received', 'confirmed', 'overdue', 'cancelled', 'error')",
            name="ck_bc_status",
        ),
        sa.CheckConstraint(
            "method IN ('boleto', 'pix', 'credit_card')",
            name="ck_bc_method",
        ),
    )
    op.create_index("ix_billing_charges_workspace", "billing_charges", ["workspace_id"])
    op.create_index(
        "ix_billing_charges_workspace_invoice",
        "billing_charges", ["workspace_id", "invoice_id"],
    )


def downgrade() -> None:
    op.drop_table("billing_charges")
    op.drop_table("billing_provider_configs")
