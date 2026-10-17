"""The audit trail: who did what, when, to which record, and what changed.

The table is **append-only**, and that is enforced by the database, not by the
application's good behaviour:

- A trigger rejects `UPDATE`, `DELETE` and `TRUNCATE`. The single exception is
  the sealing function below, which may fill in `seq`, `prev_hash` and `hash`
  of a row that has none yet.
- Every row is *sealed* into a hash chain: `hash = sha256(prev_hash || the
  row's content)`. Changing or removing a sealed row (only possible for someone
  who disabled the trigger with direct database access) breaks the chain, and
  `verify` reports where.

Sealing is separate from inserting on purpose. Chaining at insert time would
make every writing transaction queue on one lock until it commits, and two
transactions that touch the same rows in a different order would deadlock
against it. Inserting is lock-free; a periodic job (and every read of the trail)
seals whatever is not sealed yet, in order.

The rows carry no foreign keys: the trail must outlive the user or workspace it
talks about.

Access events (`core/access_log.py`) may be *anonymised* once their retention period is over: the columns
that identify a person are emptied and `purged_at` is set, and the row stays in the chain. The trigger
admits only that narrow update, and never for an event younger than `ACCESS_MIN_RETENTION_DAYS`
(`audit_events_purge_access` is the one caller). The SQL was added in migration 099.

Changing the SQL below means a new migration. `alembic/versions/093_audit_events.py`
holds a frozen copy of it.
"""
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, DateTime, Index, String, Text, event, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.access_log import ACCESS_MIN_RETENTION_DAYS, REDACTED_COLUMNS, sql_list
from app.core.database import Base

#: Stored in `actor_kind`.
ACTOR_KINDS = ("user", "api_token", "system")

#: Stored in `action`. Entity changes use the first three; the rest are named events.
ACTIONS = ("create", "update", "delete")

GENESIS_HASH = "0" * 64


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_seq", "seq", unique=True),
        Index("ix_audit_events_workspace_time", "workspace_id", "occurred_at"),
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
        Index("ix_audit_events_actor_time", "actor_user_id", "occurred_at"),
        Index("ix_audit_events_unsealed", "occurred_at", postgresql_where=text("hash IS NULL")),
        Index(
            "ix_audit_events_access",
            text("occurred_at DESC"),
            postgresql_where=text(f"action IN ({sql_list()}) AND purged_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    #: Position in the hash chain. Null until the row is sealed.
    seq: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    #: The database's clock, not the application's.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()")
    )
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    #: user | api_token | system (background jobs, migrations, sync)
    actor_kind: Mapped[str] = mapped_column(String(20), default="system")
    #: Null for facts about the instance itself (users, settings).
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(40))
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    #: {"field": [before, after]}. Secrets are masked before they get here.
    changes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    #: Free text for named events ("export", "login failed").
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prev_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    #: Set when the row was anonymised after its retention period (see `audit_events_purge_access`).
    purged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# --- SQL: digest, seal, immutability ---------------------------------------------------

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

IMMUTABLE_FUNCTION = f"""
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
       AND OLD.action IN ({sql_list()})
       AND OLD.hash IS NOT NULL
       AND OLD.purged_at IS NULL
       AND OLD.occurred_at < clock_timestamp() - interval '{ACCESS_MIN_RETENTION_DAYS} days'
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

SEAL_FUNCTION = f"""
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
    last_hash := COALESCE(last_hash, '{GENESIS_HASH}');

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

PURGE_FUNCTION = f"""
CREATE OR REPLACE FUNCTION audit_events_purge_access(retention_days integer, batch integer) RETURNS integer AS $$
DECLARE
    purged integer;
BEGIN
    PERFORM set_config('audit.purging', 'on', true);
    WITH due AS (
        SELECT id FROM audit_events
         WHERE action IN ({sql_list()})
           AND hash IS NOT NULL
           AND purged_at IS NULL
           AND occurred_at < clock_timestamp() - make_interval(days => GREATEST(retention_days, {ACCESS_MIN_RETENTION_DAYS}))
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

#: An anonymised row that still holds something the anonymising empties.
_LEFTOVERS = " OR ".join(f"e.{column} IS NOT NULL" for column in REDACTED_COLUMNS)

#: Rows whose chain link is wrong: the stored hash is not what the content gives, the link to
#: the previous row does not match, or the sequence has a hole (a row was removed). An anonymised row
#: is not re-hashed (its content is gone on purpose), but it must still look anonymised: an access event with
#: every identifying column empty, and old enough to have been anonymised at all (nothing younger than
#: `ACCESS_MIN_RETENTION_DAYS` ever is). Known limit: an OLD row relabelled the same way passes; closing that
#: needs a digest stored at anonymisation time.
VERIFY_QUERY = f"""
SELECT seq, id, reason FROM (
    SELECT e.seq, e.id,
           CASE
             WHEN e.purged_at IS NULL AND e.hash IS DISTINCT FROM audit_events_digest(e.prev_hash, e) THEN 'content changed'
             WHEN e.purged_at IS NOT NULL AND (e.action NOT IN ({sql_list()}) OR {_LEFTOVERS}
                  OR e.occurred_at > clock_timestamp() - interval '{ACCESS_MIN_RETENTION_DAYS} days') THEN 'purged row altered'
             WHEN e.prev_hash IS DISTINCT FROM COALESCE(lag(e.hash) OVER w, '{GENESIS_HASH}') THEN 'chain broken'
             WHEN e.seq IS DISTINCT FROM COALESCE(lag(e.seq) OVER w, 0) + 1 THEN 'row missing'
           END AS reason
      FROM audit_events e WHERE e.hash IS NOT NULL
    WINDOW w AS (ORDER BY e.seq)
) checked WHERE reason IS NOT NULL ORDER BY seq LIMIT 1
"""


def install_audit_ddl(connection) -> None:
    """Create the digest, seal and immutability objects. Idempotent."""
    connection.execute(text(DIGEST_FUNCTION))
    connection.execute(text(IMMUTABLE_FUNCTION))
    connection.execute(text(SEAL_FUNCTION))
    connection.execute(text(PURGE_FUNCTION))
    connection.execute(text("DROP TRIGGER IF EXISTS audit_events_no_change ON audit_events"))
    connection.execute(text("DROP TRIGGER IF EXISTS audit_events_no_truncate ON audit_events"))
    for statement in TRIGGERS:
        connection.execute(text(statement))


# `Base.metadata.create_all` (the test suite's schema) builds the table from the model, so the
# protections have to come with it. Production gets the same objects from migration 093.
event.listen(
    AuditEvent.__table__,
    "after_create",
    lambda target, connection, **kw: install_audit_ddl(connection),
)
