"""saml and scim identity columns (C6)

Revision ID: 120
Revises: 119
Create Date: 2026-10-13
"""
from alembic import op
import sqlalchemy as sa

revision: str = "120"
down_revision: str = "119"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("saml_idp_entity_id", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("saml_name_id", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("scim_external_id", sa.String(255), nullable=True))
    op.create_index("ix_users_saml_idp_entity_id", "users", ["saml_idp_entity_id"])
    op.create_index("ix_users_saml_name_id", "users", ["saml_name_id"])
    op.create_unique_constraint("uq_users_scim_external_id", "users", ["scim_external_id"])
    op.create_unique_constraint(
        "uq_users_saml_identity", "users", ["saml_idp_entity_id", "saml_name_id"]
    )
    op.add_column(
        "workspaces",
        sa.Column("scim_default_role", sa.String(40), nullable=False, server_default="editor"),
    )


def downgrade() -> None:
    op.drop_column("workspaces", "scim_default_role")
    op.drop_constraint("uq_users_saml_identity", "users", type_="unique")
    op.drop_constraint("uq_users_scim_external_id", "users", type_="unique")
    op.drop_index("ix_users_saml_name_id", table_name="users")
    op.drop_index("ix_users_saml_idp_entity_id", table_name="users")
    op.drop_column("users", "scim_external_id")
    op.drop_column("users", "saml_name_id")
    op.drop_column("users", "saml_idp_entity_id")
