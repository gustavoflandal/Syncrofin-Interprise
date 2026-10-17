"""many-to-one reconciliation: N transactions settling one invoice (A10)

Revision ID: 122
Revises: 121
Create Date: 2026-10-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "122"
down_revision: str = "121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reconciliation_suggestions",
        sa.Column("is_aggregate", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # The head transaction of an aggregate also carries its own 1:1 question
    # against the same invoice, so the pair constraint must not cover it.
    op.drop_constraint("uq_reconciliation_suggestion_pair", "reconciliation_suggestions", type_="unique")
    op.create_index(
        "uq_reconciliation_suggestion_pair",
        "reconciliation_suggestions",
        ["workspace_id", "transaction_id", "expectation_kind", "expectation_id"],
        unique=True,
        postgresql_where=sa.text("NOT is_aggregate"),
    )
    op.create_table(
        "reconciliation_suggestion_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "suggestion_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("reconciliation_suggestions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "suggestion_id", "transaction_id", name="uq_reconciliation_suggestion_member"
        ),
    )
    op.create_index(
        "ix_reconciliation_suggestion_transactions_suggestion_id",
        "reconciliation_suggestion_transactions",
        ["suggestion_id"],
    )
    op.create_index(
        "ix_reconciliation_suggestion_members_tx",
        "reconciliation_suggestion_transactions",
        ["transaction_id"],
    )


def downgrade() -> None:
    op.drop_table("reconciliation_suggestion_transactions")
    op.execute("DELETE FROM reconciliation_suggestions WHERE is_aggregate")
    op.drop_index("uq_reconciliation_suggestion_pair", table_name="reconciliation_suggestions")
    op.create_unique_constraint(
        "uq_reconciliation_suggestion_pair",
        "reconciliation_suggestions",
        ["workspace_id", "transaction_id", "expectation_kind", "expectation_id"],
    )
    op.drop_column("reconciliation_suggestions", "is_aggregate")
