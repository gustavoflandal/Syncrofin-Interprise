"""recurring_transactions: tax_obligation_type, tax_reference_code, competence_offset_months (B3)

Revision ID: 115
Revises: 114
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision: str = "115"
down_revision: str = "114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recurring_transactions",
        sa.Column("tax_obligation_type", sa.String(30), nullable=True),
    )
    op.add_column(
        "recurring_transactions",
        sa.Column("tax_reference_code", sa.String(20), nullable=True),
    )
    op.add_column(
        "recurring_transactions",
        sa.Column(
            "competence_offset_months",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_recurring_transactions_tax_type",
        "recurring_transactions",
        "tax_obligation_type IS NULL OR tax_obligation_type IN "
        "('das', 'darf_irpj', 'darf_csll', 'darf_irrf', 'darf_pis_cofins', "
        "'iss', 'inss', 'icms', 'other')",
    )
    op.create_index(
        "ix_recurring_tx_tax_type",
        "recurring_transactions",
        ["workspace_id", "tax_obligation_type"],
        postgresql_where=sa.text("tax_obligation_type IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_recurring_tx_tax_type", table_name="recurring_transactions")
    op.drop_constraint("ck_recurring_transactions_tax_type", "recurring_transactions", type_="check")
    op.drop_column("recurring_transactions", "competence_offset_months")
    op.drop_column("recurring_transactions", "tax_reference_code")
    op.drop_column("recurring_transactions", "tax_obligation_type")
