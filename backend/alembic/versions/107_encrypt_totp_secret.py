"""encrypt totp_secret at rest (C9)

Revision ID: 107
Revises: 106
Create Date: 2026-10-06
"""
import sqlalchemy as sa
from alembic import op

revision: str = "107"
down_revision: str = "106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret_enc", sa.String(500), nullable=True))

    # Data migration: encrypt every existing plaintext secret and move it to the
    # new column; clear the plaintext column so it no longer holds raw seeds.
    # Import here to avoid loading app code at migration parse time.
    from app.agents.services.crypto import encrypt  # noqa: PLC0415

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, totp_secret FROM users WHERE totp_secret IS NOT NULL")
    ).fetchall()
    for row_id, secret in rows:
        encrypted = encrypt(secret)
        conn.execute(
            sa.text(
                "UPDATE users SET totp_secret_enc = :enc, totp_secret = NULL WHERE id = :id"
            ),
            {"enc": encrypted, "id": row_id},
        )


def downgrade() -> None:
    # Re-derive plaintext from enc on the way back (best-effort; SECRET_KEY must
    # still be available).
    from app.agents.services.crypto import decrypt  # noqa: PLC0415

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, totp_secret_enc FROM users WHERE totp_secret_enc IS NOT NULL")
    ).fetchall()
    for row_id, enc in rows:
        plain = decrypt(enc)
        if plain:
            conn.execute(
                sa.text(
                    "UPDATE users SET totp_secret = :plain WHERE id = :id"
                ),
                {"plain": plain, "id": row_id},
            )

    op.drop_column("users", "totp_secret_enc")
