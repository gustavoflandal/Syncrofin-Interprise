"""transactions: client-supplied id for idempotent creation (R-1)

Revision ID: 102
Revises: 101

Lets a client (the mobile app's offline queue) tag a transaction it creates with an id it generated
itself. A retry after a dropped connection resends the same id; the unique index below makes the
second insert impossible, so `transaction_service.create_transaction` can detect the collision and
hand back the existing row instead of creating a duplicate. See docs/ENTERPRISE.md §9, R-1.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "102"
down_revision: Union[str, None] = "101"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("client_id", UUID(as_uuid=True), nullable=True))
    op.create_index(
        "ux_transactions_workspace_client_id",
        "transactions",
        ["workspace_id", "client_id"],
        unique=True,
        postgresql_where=sa.text("client_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_transactions_workspace_client_id", table_name="transactions")
    op.drop_column("transactions", "client_id")
