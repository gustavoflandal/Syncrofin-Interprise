"""data subject requests: the D1 titular's-channel table

Revision ID: 100
Revises: 099
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "100"
down_revision: Union[str, None] = "099"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_subject_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("protocol", sa.String(20), unique=True, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('access', 'portability', 'correction', 'erasure')",
            name="ck_data_subject_requests_kind",
        ),
        sa.CheckConstraint(
            "status IN ('resolved_auto', 'pending', 'resolved_manual', 'rejected')",
            name="ck_data_subject_requests_status",
        ),
    )
    op.create_index(
        "ix_data_subject_requests_user_time", "data_subject_requests", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_data_subject_requests_due",
        "data_subject_requests",
        ["due_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_data_subject_requests_due", table_name="data_subject_requests")
    op.drop_index("ix_data_subject_requests_user_time", table_name="data_subject_requests")
    op.drop_table("data_subject_requests")
