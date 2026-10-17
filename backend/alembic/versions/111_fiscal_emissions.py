"""fiscal provider config e emissões de NF-e (B1)

Revision ID: 111
Revises: 110
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "111"
down_revision: str = "110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fiscal_provider_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False, server_default="homologation"),
        sa.Column("api_key_encrypted", sa.Text, nullable=False),
        sa.Column("cnpj_emitente", sa.String(14), nullable=True),
        sa.Column("serie_padrao", sa.String(5), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("workspace_id", name="uq_fiscal_provider_config_workspace"),
        sa.CheckConstraint(
            "provider IN ('focus_nfe', 'enotas', 'plugnotas')",
            name="ck_fiscal_provider",
        ),
        sa.CheckConstraint(
            "environment IN ('homologation', 'production')",
            name="ck_fiscal_provider_env",
        ),
    )

    op.create_table(
        "fiscal_emissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("provider_ref", sa.String(100), nullable=True),
        sa.Column("chave_acesso", sa.String(44), nullable=True, index=True),
        sa.Column("nfe_number", sa.String(20), nullable=True),
        sa.Column("nfe_serie", sa.String(5), nullable=True),
        sa.Column("xml_url", sa.Text, nullable=True),
        sa.Column("pdf_url", sa.Text, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Index("ix_fiscal_emissions_workspace_invoice", "workspace_id", "invoice_id"),
        sa.Index("ix_fiscal_emissions_workspace_status", "workspace_id", "status"),
        sa.CheckConstraint(
            "provider IN ('focus_nfe', 'enotas', 'plugnotas')",
            name="ck_fe_provider",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'issued', 'cancelled', 'error')",
            name="ck_fe_status",
        ),
        sa.CheckConstraint(
            "environment IN ('homologation', 'production')",
            name="ck_fe_environment",
        ),
    )


def downgrade() -> None:
    op.drop_table("fiscal_emissions")
    op.drop_table("fiscal_provider_configs")
