"""roles a workspace's owner makes for that workspace, and room for their keys in the member's role

Revision ID: 096
Revises: 095
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "096"
down_revision: Union[str, None] = "095"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("permissions", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "key", name="uq_workspace_role_key"),
        sa.UniqueConstraint("workspace_id", "name", name="uq_workspace_role_name"),
    )
    op.create_index("ix_workspace_roles_workspace_id", "workspace_roles", ["workspace_id"])
    # A member holds a custom role by its key ("c_" + 8 hex digits): the column gets room for it.
    op.alter_column("workspace_members", "role", existing_type=sa.String(20), type_=sa.String(40))


def downgrade() -> None:
    op.drop_table("workspace_roles")
    op.alter_column("workspace_members", "role", existing_type=sa.String(40), type_=sa.String(20))
