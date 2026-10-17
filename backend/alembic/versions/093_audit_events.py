"""audit trail: the append-only audit_events table, its hash chain and its guards

Revision ID: 093
Revises: 092

The SQL below is a frozen copy of what `app/models/audit.py` installs for the test suite. If the
trail's SQL has to change, add a migration; do not edit this one.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "093"
down_revision: Union[str, None] = "092"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DIGEST_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_events_digest(prev text, e audit_events) RETURNS text AS $$
    SELECT encode(sha256(convert_to(concat_ws('|',
        prev,
        e.seq,
        e.id,
        to_char(e.occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'),
        e.actor_user_id,
        e.actor_kind,
        e.workspace_id,
        e.action,
        e.entity_type,
        e.entity_id,
        e.changes::text,
        e.ip,
        e.request_id,
        e.detail
    ), 'UTF8')), 'hex')
$$ LANGUAGE sql STABLE
"""

IMMUTABLE_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS trigger AS $$
BEGIN
    -- The sealing function may fill in the chain columns of a row that has none yet.
    IF TG_OP = 'UPDATE'
       AND OLD.hash IS NULL
       AND current_setting('audit.sealing', true) = 'on'
       AND (to_jsonb(NEW) - 'seq' - 'prev_hash' - 'hash') = (to_jsonb(OLD) - 'seq' - 'prev_hash' - 'hash')
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'audit_events is append-only (% refused)', TG_OP USING ERRCODE = '42501';
END
$$ LANGUAGE plpgsql
"""

SEAL_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_events_seal() RETURNS integer AS $$
DECLARE
    r audit_events%ROWTYPE;
    last_seq bigint;
    last_hash text;
    sealed integer := 0;
BEGIN
    -- One sealer at a time; a concurrent call simply does nothing.
    IF NOT pg_try_advisory_xact_lock(7240001) THEN
        RETURN 0;
    END IF;
    PERFORM set_config('audit.sealing', 'on', true);

    SELECT seq, hash INTO last_seq, last_hash
      FROM audit_events WHERE hash IS NOT NULL ORDER BY seq DESC LIMIT 1;
    last_seq := COALESCE(last_seq, 0);
    last_hash := COALESCE(last_hash, '0000000000000000000000000000000000000000000000000000000000000000');

    FOR r IN SELECT * FROM audit_events WHERE hash IS NULL ORDER BY occurred_at, id LOOP
        last_seq := last_seq + 1;
        r.seq := last_seq;
        r.prev_hash := last_hash;
        r.hash := audit_events_digest(last_hash, r);
        UPDATE audit_events SET seq = r.seq, prev_hash = r.prev_hash, hash = r.hash WHERE id = r.id;
        last_hash := r.hash;
        sealed := sealed + 1;
    END LOOP;
    RETURN sealed;
END
$$ LANGUAGE plpgsql
"""

TRIGGERS = (
    """
    CREATE TRIGGER audit_events_no_change
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION audit_events_immutable()
    """,
    """
    CREATE TRIGGER audit_events_no_truncate
        BEFORE TRUNCATE ON audit_events
        FOR EACH STATEMENT EXECUTE FUNCTION audit_events_immutable()
    """,
)


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("seq", sa.BigInteger(), nullable=True),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False
        ),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_kind", sa.String(20), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=True),
        sa.Column("changes", postgresql.JSONB(), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(300), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=True),
        sa.Column("hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_audit_events_seq", "audit_events", ["seq"], unique=True)
    op.create_index("ix_audit_events_workspace_time", "audit_events", ["workspace_id", "occurred_at"])
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"])
    op.create_index("ix_audit_events_actor_time", "audit_events", ["actor_user_id", "occurred_at"])
    op.create_index(
        "ix_audit_events_unsealed", "audit_events", ["occurred_at"], postgresql_where=sa.text("hash IS NULL")
    )
    op.execute(DIGEST_FUNCTION)
    op.execute(IMMUTABLE_FUNCTION)
    op.execute(SEAL_FUNCTION)
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade() -> None:
    # Dropping the table is the one thing the trigger does not guard (it is DDL, not a row
    # change): an operator who rolls the migration back has decided to discard the trail.
    op.execute("DROP FUNCTION IF EXISTS audit_events_seal()")
    op.execute("DROP FUNCTION IF EXISTS audit_events_digest(text, audit_events)")
    op.drop_table("audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_immutable()")
