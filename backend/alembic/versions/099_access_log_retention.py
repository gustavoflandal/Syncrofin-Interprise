"""access log retention: anonymise access events after their retention period

Revision ID: 099
Revises: 098

The SQL below is a frozen copy of what `app/models/audit.py` installs for the test suite (a test compares
them). If it has to change, add a migration; do not edit this one.

Deploy: the CREATE INDEX is not CONCURRENTLY, so it blocks writes to `audit_events` while it runs: plan the deploy.
Downgrade: refused once any access event was anonymised (`purged_at`), because the previous `verify` would flag
those rows as tampered.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "099"
down_revision: Union[str, None] = "098"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

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
    -- The purge function may anonymise an access event once its retention period is over: the columns that
    -- identify a person are emptied and nothing else changes. Nothing younger than the floor qualifies.
    IF TG_OP = 'UPDATE'
       AND current_setting('audit.purging', true) = 'on'
       AND OLD.action IN ('login', 'login_failed', 'login_blocked', 'account_locked', 'account_unlocked', 'session_revoked', 'token_access')
       AND OLD.hash IS NOT NULL
       AND OLD.purged_at IS NULL
       AND OLD.occurred_at < clock_timestamp() - interval '183 days'
       AND NEW.purged_at IS NOT NULL
       AND NEW.actor_user_id IS NULL AND NEW.entity_id IS NULL AND NEW.changes IS NULL
       AND NEW.ip IS NULL AND NEW.user_agent IS NULL AND NEW.request_id IS NULL AND NEW.detail IS NULL
       AND (to_jsonb(NEW) - 'actor_user_id' - 'entity_id' - 'changes' - 'ip' - 'user_agent' - 'request_id' - 'detail' - 'purged_at')
         = (to_jsonb(OLD) - 'actor_user_id' - 'entity_id' - 'changes' - 'ip' - 'user_agent' - 'request_id' - 'detail' - 'purged_at')
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'audit_events is append-only (% refused)', TG_OP USING ERRCODE = '42501';
END
$$ LANGUAGE plpgsql
"""

#: What migration 093 installed, for `downgrade`.
PREVIOUS_IMMUTABLE_FUNCTION = """
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

PURGE_FUNCTION = """
CREATE OR REPLACE FUNCTION audit_events_purge_access(retention_days integer, batch integer) RETURNS integer AS $$
DECLARE
    purged integer;
BEGIN
    PERFORM set_config('audit.purging', 'on', true);
    WITH due AS (
        SELECT id FROM audit_events
         WHERE action IN ('login', 'login_failed', 'login_blocked', 'account_locked', 'account_unlocked', 'session_revoked', 'token_access')
           AND hash IS NOT NULL
           AND purged_at IS NULL
           AND occurred_at < clock_timestamp() - make_interval(days => GREATEST(retention_days, 183))
         ORDER BY occurred_at, id
         LIMIT batch
         FOR UPDATE SKIP LOCKED
    )
    UPDATE audit_events e
       SET actor_user_id = NULL, entity_id = NULL, changes = NULL, ip = NULL,
           user_agent = NULL, request_id = NULL, detail = NULL, purged_at = clock_timestamp()
      FROM due
     WHERE e.id = due.id AND e.purged_at IS NULL;
    GET DIAGNOSTICS purged = ROW_COUNT;
    PERFORM set_config('audit.purging', 'off', true);
    RETURN purged;
END
$$ LANGUAGE plpgsql
"""

ACCESS_INDEX = """
CREATE INDEX IF NOT EXISTS ix_audit_events_access ON audit_events (occurred_at DESC)
 WHERE action IN ('login', 'login_failed', 'login_blocked', 'account_locked', 'account_unlocked', 'session_revoked', 'token_access')
   AND purged_at IS NULL
"""


def upgrade() -> None:
    op.add_column("audit_events", sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(IMMUTABLE_FUNCTION)
    op.execute(PURGE_FUNCTION)
    op.execute(ACCESS_INDEX)


def downgrade() -> None:
    # The guard reads the database, which offline mode (--sql) has not got.
    if not op.get_context().as_sql and op.get_bind().execute(
        sa.text("SELECT 1 FROM audit_events WHERE purged_at IS NOT NULL LIMIT 1")
    ).first():
        raise RuntimeError(
            "Cannot downgrade: some access events were already anonymised (purged_at); "
            "the previous verify would flag them as tampered"
        )
    op.execute("DROP INDEX IF EXISTS ix_audit_events_access")
    op.execute("DROP FUNCTION IF EXISTS audit_events_purge_access(integer, integer)")
    op.execute(PREVIOUS_IMMUTABLE_FUNCTION)
    op.drop_column("audit_events", "purged_at")
