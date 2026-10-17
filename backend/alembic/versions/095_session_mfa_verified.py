"""sessions: whether the session has proved a second factor

Revision ID: 095
Revises: 094
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "095"
down_revision: Union[str, None] = "094"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_sessions",
        sa.Column("mfa_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Sessions that signed in with a second factor already carry one.
    op.execute("UPDATE user_sessions SET mfa_verified = true WHERE auth_method IN ('2fa', 'passkey', 'oidc')")


def downgrade() -> None:
    op.drop_column("user_sessions", "mfa_verified")
