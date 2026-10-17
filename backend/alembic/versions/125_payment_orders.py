"""payment orders and approval events (F4)

Revision ID: 125
Revises: 124
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "125"
down_revision: str = "124"
branch_labels = None
depends_on = None


def _uuid(name: str, **kw):
    return sa.Column(name, postgresql.UUID(as_uuid=True), **kw)


def upgrade() -> None:
    op.create_table(
        "payment_orders",
        _uuid("id", primary_key=True),
        _uuid("workspace_id", nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="BRL"),
        sa.Column("description", sa.String(500)),
        sa.Column("beneficiary_name", sa.String(255), nullable=False),
        sa.Column("beneficiary_tax_id", sa.String(20)),
        sa.Column("pix_key", sa.String(255)),
        sa.Column("pix_key_type", sa.String(20)),
        sa.Column("bank_code", sa.String(10)),
        sa.Column("branch", sa.String(10)),
        sa.Column("account_number", sa.String(20)),
        sa.Column("account_type", sa.String(10)),
        _uuid("source_account_id"),
        _uuid("invoice_id"),
        _uuid("payee_id"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("approval_status", sa.String(20), nullable=False, server_default="none"),
        _uuid("created_by_user_id", nullable=False),
        _uuid("first_approver_id"),
        sa.Column("first_approved_at", sa.DateTime(timezone=True)),
        _uuid("second_approver_id"),
        sa.Column("second_approved_at", sa.DateTime(timezone=True)),
        _uuid("sent_by_user_id"),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("provider", sa.String(50)),
        sa.Column("external_id", sa.String(255)),
        sa.Column("provider_error", sa.Text()),
        sa.Column("receipt_url", sa.String(500)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        _uuid("transaction_id"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payee_id"], ["payees.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["first_approver_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["second_approver_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["sent_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("workspace_id", "idempotency_key", name="uq_payment_order_idempotency"),
        sa.CheckConstraint("amount > 0", name="ck_payment_order_positive"),
    )
    op.create_index("ix_payment_orders_workspace_id", "payment_orders", ["workspace_id"])
    op.create_index("ix_payment_orders_workspace_status", "payment_orders", ["workspace_id", "status"])
    op.create_index("ix_payment_orders_external_id", "payment_orders", ["external_id"])

    op.create_table(
        "payment_approval_events",
        _uuid("id", primary_key=True),
        _uuid("payment_order_id", nullable=False),
        _uuid("workspace_id", nullable=False),
        _uuid("user_id", nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["payment_order_id"], ["payment_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_payment_approval_events_payment_order_id", "payment_approval_events", ["payment_order_id"])
    op.create_index("ix_payment_approval_events_workspace_id", "payment_approval_events", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("payment_approval_events")
    op.drop_table("payment_orders")
