# Registros de acesso (D3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Registro de acessos para o administrador, histórico de acessos para cada pessoa, uso de token de API registrado, e guarda dos registros com prazo configurável e anonimização automática.

**Architecture:** Os eventos de acesso continuam em `audit_events` (append-only, cadeia de hashes). Um conjunto fixo de ações (`ACCESS_ACTIONS`) define o que é "acesso". O descarte **anonimiza** a linha (zera as colunas pessoais e marca `purged_at`) em vez de apagá-la, para a cadeia continuar verificável; o trigger do banco só admite essa exceção estreita e impõe o piso de 183 dias. O prazo vive em `app_settings` e é editado em Administração.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, PostgreSQL (plpgsql), Alembic, Celery, Redis, React 19 + TanStack Query + i18next + vitest.

Spec: [2026-09-21-registros-de-acesso-design.md](../specs/2026-09-21-registros-de-acesso-design.md)

## Global Constraints

- Ações de acesso: `("login", "login_failed", "login_blocked", "account_locked", "account_unlocked", "session_revoked", "token_access")`.
- Prazo de guarda: chave `access_log_retention_days` em `app_settings`; padrão `183` (env `ACCESS_LOG_RETENTION_DAYS`); aceito de `183` a `3650`; o banco nunca anonimiza evento com menos de 183 dias.
- Colunas anonimizadas: `actor_user_id, entity_id, changes, ip, user_agent, request_id, detail` (+ `purged_at` preenchido).
- `token_access`: no máximo 1 evento por par (token, IP) por hora (`SET NX EX 3600` no Redis); falha do Redis grava o evento mesmo assim; token inválido não gera evento.
- Descarte: tarefa Celery diária `app.tasks.audit_tasks.purge_access_log`, lotes de 10.000; grava `access_log_purged` (ator system) se anonimizou algo; esse evento não pertence a `ACCESS_ACTIONS`.
- Limites de API: lista do administrador `limit ≤ 200`, histórico próprio `limit ≤ 100`, CSV até 100.000 linhas; `action` fora do conjunto → 422.
- Consultas e histórico ignoram linhas anonimizadas (`purged_at IS NULL`).
- Só idiomas en, pt-BR, es; toda chave nova nos três (`npm run i18n:check -- --strict`).
- Testes só em PostgreSQL real (`docker compose -f docker-compose.test.yml up -d`, porta 55433).
- Windows: repositório com autocrlf. Edições por script Python usam `encoding='utf-8', newline=''`. A ferramenta Edit com `old_string` de **uma linha só** funciona em arquivo CRLF (o `new_string` pode ter várias linhas; linhas LF misturadas são inofensivas, o git normaliza). Não use `old_string` de várias linhas em arquivo CRLF.
- Trabalho na branch `feat/registros-de-acesso` (já criada, spec commitado). Todo commit termina com a linha `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`. Nunca commitar `.env`, `secrets/`, `docker-compose.override.yml`.
- Comandos de backend rodam em `D:\Projeto Finance\FinanceBR-Interprise\backend`: `TZ=UTC0 .venv/Scripts/python.exe -m pytest <alvo> -n 4 -q -p no:cacheprovider`. Comandos de frontend em `frontend/`.

## File Structure

Backend
- Create `backend/app/core/access_log.py`: constantes (ações, prazos, colunas) e `sql_list()`.
- Modify `backend/app/models/audit.py`: coluna `purged_at`, índice parcial, trigger com a exceção de anonimização, função `audit_events_purge_access`, `VERIFY_QUERY`.
- Create `backend/alembic/versions/099_access_log_retention.py`: cópia congelada do SQL acima.
- Create `backend/app/services/access_log_service.py`: `record_token_access`, `retention_days`, `set_retention_days`, `purge_expired`.
- Modify `backend/app/services/api_token_service.py`: chama `record_token_access` em `authenticate`.
- Modify `backend/app/core/config.py`: `access_log_retention_days`.
- Modify `backend/app/tasks/audit_tasks.py` e `backend/app/worker.py`: tarefa e agenda diária.
- Create `backend/app/api/access_log.py` e modify `backend/app/main.py`: rotas.
- Modify `backend/tests/conftest.py`: patch do Redis do novo serviço.
- Create tests: `tests/access_log_helpers.py`, `test_access_log_guard.py`, `test_token_access.py`, `test_access_log_retention.py`, `test_access_log_api.py`; modify `test_write_permission_coverage.py`.
- Modify `docker-compose.prod.yml`: `ACCESS_LOG_RETENTION_DAYS`.

Frontend
- Create `frontend/src/lib/access-log.ts` (+ test): rótulos de ação e motivo.
- Modify `frontend/src/types/index.ts`, `frontend/src/lib/api.ts`.
- Create `frontend/src/pages/admin/access-log.tsx` (+ test); modify `frontend/src/App.tsx`.
- Create `frontend/src/components/admin/access-retention-card.tsx` (+ test); modify `frontend/src/pages/admin/settings.tsx`.
- Modify `frontend/src/components/sessions-dialog.tsx` (+ test).
- Modify `frontend/src/locales/{en,es,pt-BR}.json`; help `administracao.md`, `seguranca-conta.md`; regenerate `docs/MANUAL.md`.

Docs: `docs/FEATURES.md` (§15), `CONFIGURATION.md`, `ENTERPRISE.md`, `FASE1.md`.

---

### Task 1: Coluna, trigger, função de descarte e migração

**Files:**
- Create: `backend/app/core/access_log.py`
- Create: `backend/tests/access_log_helpers.py`
- Create: `backend/tests/test_access_log_guard.py`
- Modify: `backend/app/models/audit.py`
- Create: `backend/alembic/versions/099_access_log_retention.py`

**Interfaces:**
- Produces: `app.core.access_log.ACCESS_ACTIONS: tuple[str, ...]`, `ACCESS_MIN_RETENTION_DAYS = 183`, `ACCESS_MAX_RETENTION_DAYS = 3650`, `REDACTED_COLUMNS: tuple[str, ...]`, `sql_list() -> str`.
- Produces: `AuditEvent.purged_at`; SQL `audit_events_purge_access(retention_days integer, batch integer) RETURNS integer`; `tests.access_log_helpers.add_event(session, *, action="login", age_days=0, actor_user_id=RANDOM, actor_kind="user", entity_type="user_session", entity_id="e1", workspace_id=None, ip="198.51.100.7", user_agent="Firefox", detail="password", seal_it=True) -> uuid.UUID`.

- [ ] **Step 1: Create the constants module**

`backend/app/core/access_log.py`:

```python
"""Which audit events are *accesses* to the application, and how long they are kept.

An access is somebody (or a token) getting in, failing to, being held back, or being shown out. These
events live in `audit_events` like every other, and are read through the access-log routes.

Keeping them: the law asks for at least six months (Marco Civil da Internet, art. 15), and the data
protection law asks for no longer than needed. So the instance has a **retention period**
(`access_log_retention_days`, in `app_settings`, never below `ACCESS_MIN_RETENTION_DAYS`), and once it is
over an event is **anonymised**, not deleted: the columns that identify a person are emptied and the row
stays, so the hash chain of the trail still verifies. The database enforces the floor: its trigger refuses
to anonymise anything younger than `ACCESS_MIN_RETENTION_DAYS`.

The action list is repeated in SQL (the trigger, `audit_events_purge_access` and the index
`ix_audit_events_access`). Adding an action means a new migration for all three, and a test compares them.
"""
from __future__ import annotations

ACCESS_ACTIONS: tuple[str, ...] = (
    "login",
    "login_failed",
    "login_blocked",
    "account_locked",
    "account_unlocked",
    "session_revoked",
    "token_access",
)

ACCESS_MIN_RETENTION_DAYS = 183
ACCESS_MAX_RETENTION_DAYS = 3650

#: What anonymising empties. Everything else on the row (time, action, kind of actor, workspace, hashes) stays.
REDACTED_COLUMNS: tuple[str, ...] = (
    "actor_user_id",
    "entity_id",
    "changes",
    "ip",
    "user_agent",
    "request_id",
    "detail",
)


def sql_list() -> str:
    """The actions as SQL literals: `'login', 'login_failed', ...`."""
    return ", ".join(f"'{action}'" for action in ACCESS_ACTIONS)
```

- [ ] **Step 2: Create the test helper**

`backend/tests/access_log_helpers.py`:

```python
"""Building audit events of any age for the access-log tests."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import seal
from app.models.audit import AuditEvent

#: Default for `actor_user_id`: a fresh person nobody else shares (pass None for "no actor").
RANDOM: object = object()


async def add_event(
    session: AsyncSession,
    *,
    action: str = "login",
    age_days: float = 0,
    actor_user_id: object = RANDOM,
    actor_kind: str = "user",
    entity_type: str = "user_session",
    entity_id: str | None = "e1",
    workspace_id: uuid.UUID | None = None,
    ip: str | None = "198.51.100.7",
    user_agent: str | None = "Firefox",
    detail: str | None = "password",
    seal_it: bool = True,
) -> uuid.UUID:
    """Insert one event `age_days` old, and (by default) seal it into the chain."""
    event_id = uuid.uuid4()
    actor = uuid.uuid4() if actor_user_id is RANDOM else actor_user_id
    await session.execute(
        insert(AuditEvent.__table__).values(
            id=event_id,
            occurred_at=datetime.now(timezone.utc) - timedelta(days=age_days),
            actor_user_id=actor,
            actor_kind=actor_kind,
            workspace_id=workspace_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            ip=ip,
            user_agent=user_agent,
            request_id="req-1",
            detail=detail,
        )
    )
    await session.commit()
    if seal_it:
        await seal(session)
    return event_id
```

- [ ] **Step 3: Write the failing tests**

`backend/tests/test_access_log_guard.py`:

```python
"""Anonymising an access event: what the database allows, what it refuses, and that the chain still verifies."""
import importlib.util
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_log import ACCESS_ACTIONS, REDACTED_COLUMNS
from app.models import audit as audit_module
from app.models.audit import VERIFY_QUERY
from tests.access_log_helpers import add_event

pytestmark = pytest.mark.asyncio

BACKEND = Path(__file__).resolve().parents[1]
REDACT = ", ".join(f"{column} = NULL" for column in REDACTED_COLUMNS) + ", purged_at = now()"


@pytest_asyncio.fixture(autouse=True)
async def _empty_trail(clean_db):
    yield


async def _redact(session: AsyncSession, event_id: uuid.UUID, *, flag: bool = True, set_clause: str = REDACT) -> None:
    if flag:
        await session.execute(text("SELECT set_config('audit.purging', 'on', true)"))
    await session.execute(text(f"UPDATE audit_events SET {set_clause} WHERE id = :id"), {"id": event_id})


async def _refused(session: AsyncSession, event_id: uuid.UUID, **kwargs) -> None:
    with pytest.raises(DBAPIError, match="append-only"):
        await _redact(session, event_id, **kwargs)
    await session.rollback()


async def _purge(session: AsyncSession, days: int, batch: int = 1000) -> int:
    done = (
        await session.execute(text("SELECT audit_events_purge_access(:d, :b)"), {"d": days, "b": batch})
    ).scalar_one()
    await session.commit()
    return done


class TestWhatTheDatabaseAllows:
    async def test_an_old_sealed_access_event_can_be_anonymised(self, session: AsyncSession):
        event_id = await add_event(session, action="login_failed", age_days=200)

        await _redact(session, event_id)
        await session.commit()

        row = (await session.execute(text("SELECT * FROM audit_events WHERE id = :id"), {"id": event_id})).mappings().one()
        for column in REDACTED_COLUMNS:
            assert row[column] is None, column
        assert row["purged_at"] is not None
        assert row["action"] == "login_failed" and row["hash"] and row["seq"] == 1

    async def test_nothing_younger_than_the_floor_qualifies(self, session: AsyncSession):
        await _refused(session, await add_event(session, age_days=100))

    async def test_only_access_events_qualify(self, session: AsyncSession):
        await _refused(session, await add_event(session, action="update", entity_type="accounts", age_days=400))

    async def test_an_unsealed_event_does_not_qualify(self, session: AsyncSession):
        await _refused(session, await add_event(session, age_days=400, seal_it=False))

    async def test_it_needs_the_purge_flag(self, session: AsyncSession):
        await _refused(session, await add_event(session, age_days=400), flag=False)

    async def test_no_other_column_may_change_with_it(self, session: AsyncSession):
        await _refused(session, await add_event(session, age_days=400), set_clause=REDACT + ", action = 'login'")

    async def test_every_identifying_column_must_be_emptied(self, session: AsyncSession):
        kept_ip = "actor_user_id = NULL, entity_id = NULL, changes = NULL, user_agent = NULL, request_id = NULL, detail = NULL, purged_at = now()"
        await _refused(session, await add_event(session, age_days=400), set_clause=kept_ip)

    async def test_it_happens_once(self, session: AsyncSession):
        event_id = await add_event(session, age_days=400)
        await _redact(session, event_id)
        await session.commit()
        await _refused(session, event_id)


class TestThePurgeFunction:
    async def test_it_never_goes_below_the_floor(self, session: AsyncSession):
        await add_event(session, age_days=100)
        assert await _purge(session, 10) == 0

    async def test_it_honours_a_longer_period(self, session: AsyncSession):
        await add_event(session, age_days=300)
        await add_event(session, age_days=200)
        assert await _purge(session, 250) == 1
        assert await _purge(session, 183) == 1

    async def test_it_works_in_batches(self, session: AsyncSession):
        for _ in range(3):
            await add_event(session, age_days=400)
        assert await _purge(session, 183, batch=2) == 2
        assert await _purge(session, 183, batch=2) == 1

    async def test_it_leaves_other_events_alone(self, session: AsyncSession):
        other = await add_event(session, action="update", entity_type="accounts", age_days=400)
        assert await _purge(session, 183) == 0
        purged = (await session.execute(text("SELECT purged_at FROM audit_events WHERE id = :id"), {"id": other})).scalar_one()
        assert purged is None


class TestTheChain:
    async def test_it_still_verifies_after_an_anonymisation(self, session: AsyncSession):
        await add_event(session, age_days=400)
        await add_event(session, age_days=300)
        await add_event(session, age_days=1)
        assert await _purge(session, 183) == 2
        assert (await session.execute(text(VERIFY_QUERY))).first() is None

    async def test_tampering_with_a_live_row_is_still_caught(self, session: AsyncSession):
        await add_event(session, age_days=400)
        live = await add_event(session, age_days=1)
        await _purge(session, 183)

        await session.execute(text("ALTER TABLE audit_events DISABLE TRIGGER USER"))
        await session.execute(text("UPDATE audit_events SET ip = '203.0.113.99' WHERE id = :id"), {"id": live})
        await session.execute(text("ALTER TABLE audit_events ENABLE TRIGGER USER"))
        await session.commit()

        found = (await session.execute(text(VERIFY_QUERY))).first()
        assert found is not None and found.reason == "content changed"

    async def test_removing_an_anonymised_row_is_still_caught(self, session: AsyncSession):
        await add_event(session, age_days=500)
        middle = await add_event(session, age_days=400)
        await add_event(session, age_days=1)
        await _purge(session, 183)

        await session.execute(text("ALTER TABLE audit_events DISABLE TRIGGER USER"))
        await session.execute(text("DELETE FROM audit_events WHERE id = :id"), {"id": middle})
        await session.execute(text("ALTER TABLE audit_events ENABLE TRIGGER USER"))
        await session.commit()

        found = (await session.execute(text(VERIFY_QUERY))).first()
        assert found is not None and found.reason in ("chain broken", "row missing")


class TestTheSqlAgrees:
    async def test_trigger_function_and_index_name_every_access_action(self, session: AsyncSession):
        definitions = [
            (await session.execute(text("SELECT pg_get_functiondef('audit_events_immutable'::regproc)"))).scalar_one(),
            (
                await session.execute(
                    text("SELECT pg_get_functiondef('audit_events_purge_access(integer,integer)'::regprocedure)")
                )
            ).scalar_one(),
            (await session.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_audit_events_access'"))).scalar_one(),
        ]
        for definition in definitions:
            for action in ACCESS_ACTIONS:
                assert f"'{action}'" in definition, action
        assert "purged_at IS NULL" in definitions[2]

    def test_the_migration_holds_the_same_sql_as_the_models(self):
        path = BACKEND / "alembic" / "versions" / "099_access_log_retention.py"
        spec = importlib.util.spec_from_file_location("migration_099", path)
        assert spec is not None and spec.loader is not None
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        def flat(sql: str) -> str:
            return " ".join(sql.split())

        assert flat(migration.IMMUTABLE_FUNCTION) == flat(audit_module.IMMUTABLE_FUNCTION)
        assert flat(migration.PURGE_FUNCTION) == flat(audit_module.PURGE_FUNCTION)

    def test_no_code_removes_rows_from_the_trail(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in (BACKEND / "app").rglob("*.py"))
        assert "DELETE FROM audit_events" not in source
        assert "delete(AuditEvent" not in source
```

- [ ] **Step 4: Run the tests to verify they fail**

Run (in `backend/`): `TZ=UTC0 .venv/Scripts/python.exe -m pytest tests/test_access_log_guard.py -q -p no:cacheprovider`
Expected: collection or test errors (`purged_at`, `audit_events_purge_access` and the migration do not exist yet).

- [ ] **Step 5: Update `models/audit.py`**

Each edit below uses a one-line `old_string` (the file is CRLF).

1. Docstring: replace the line ``Changing the SQL below means a new migration. `alembic/versions/093_audit_events.py` `` (that exact line, without the trailing space) with:

```
Access events (`core/access_log.py`) may be *anonymised* once their retention period is over: the columns
that identify a person are emptied and `purged_at` is set, and the row stays in the chain. The trigger
admits only that narrow update, and never for an event younger than `ACCESS_MIN_RETENTION_DAYS`
(`audit_events_purge_access` is the one caller). The SQL was added in migration 099.

Changing the SQL below means a new migration. `alembic/versions/093_audit_events.py`
```

2. Import: replace `from app.core.database import Base` with:

```python
from app.core.access_log import ACCESS_MIN_RETENTION_DAYS, sql_list
from app.core.database import Base
```

3. Index: replace the line `        Index("ix_audit_events_unsealed", "occurred_at", postgresql_where=text("hash IS NULL")),` with itself plus:

```python
        Index("ix_audit_events_unsealed", "occurred_at", postgresql_where=text("hash IS NULL")),
        Index(
            "ix_audit_events_access",
            text("occurred_at DESC"),
            postgresql_where=text(f"action IN ({sql_list()}) AND purged_at IS NULL"),
        ),
```

4. Column: replace the line `    hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)` (four leading spaces; not the `prev_hash` line) with itself plus:

```python
    hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    #: Set when the row was anonymised after its retention period (see `audit_events_purge_access`).
    purged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

5. Trigger: replace the line `IMMUTABLE_FUNCTION = """` with `IMMUTABLE_FUNCTION = f"""`, then replace the line `    RAISE EXCEPTION 'audit_events is append-only (% refused)', TG_OP USING ERRCODE = '42501';` with:

```
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
```

6. Purge function: replace the line `TRIGGERS = (` with:

```python
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
    )
    UPDATE audit_events e
       SET actor_user_id = NULL, entity_id = NULL, changes = NULL, ip = NULL,
           user_agent = NULL, request_id = NULL, detail = NULL, purged_at = clock_timestamp()
      FROM due
     WHERE e.id = due.id;
    GET DIAGNOSTICS purged = ROW_COUNT;
    RETURN purged;
END
$$ LANGUAGE plpgsql
"""

TRIGGERS = (
```

7. Verify: replace the line `             WHEN e.hash IS DISTINCT FROM audit_events_digest(e.prev_hash, e) THEN 'content changed'` with:

```
             WHEN e.purged_at IS NULL AND e.hash IS DISTINCT FROM audit_events_digest(e.prev_hash, e) THEN 'content changed'
```

8. Install: replace the line `    connection.execute(text(SEAL_FUNCTION))` with itself plus `    connection.execute(text(PURGE_FUNCTION))`.

- [ ] **Step 6: Create the migration**

`backend/alembic/versions/099_access_log_retention.py` (the SQL is a frozen copy of what `models/audit.py` installs; if it ever has to change, add a migration):

```python
"""access log retention: anonymise access events after their retention period

Revision ID: 099
Revises: 098

The SQL below is a frozen copy of what `app/models/audit.py` installs for the test suite (a test compares
them). If it has to change, add a migration; do not edit this one.
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
    )
    UPDATE audit_events e
       SET actor_user_id = NULL, entity_id = NULL, changes = NULL, ip = NULL,
           user_agent = NULL, request_id = NULL, detail = NULL, purged_at = clock_timestamp()
      FROM due
     WHERE e.id = due.id;
    GET DIAGNOSTICS purged = ROW_COUNT;
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
    op.execute("DROP INDEX IF EXISTS ix_audit_events_access")
    op.execute("DROP FUNCTION IF EXISTS audit_events_purge_access(integer, integer)")
    op.execute(PREVIOUS_IMMUTABLE_FUNCTION)
    op.drop_column("audit_events", "purged_at")
```

- [ ] **Step 7: Run the tests, ruff, the migration chain and the audit regressions**

Run (in `backend/`):
```
TZ=UTC0 .venv/Scripts/python.exe -m pytest tests/test_access_log_guard.py tests/test_audit.py tests/test_audit_coverage.py -n 4 -q -p no:cacheprovider
.venv/Scripts/ruff.exe check .
.venv/Scripts/python.exe scripts/check_migration_chain.py
```
Expected: all tests pass (the guard file has 18 tests), `All checks passed!`, `single line ... head 099`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/access_log.py backend/app/models/audit.py backend/alembic/versions/099_access_log_retention.py backend/tests/access_log_helpers.py backend/tests/test_access_log_guard.py
git commit -m "feat: anonimização de eventos de acesso após o prazo, com piso no banco (D3)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 2: Evento `token_access`

**Files:**
- Create: `backend/app/services/access_log_service.py`
- Modify: `backend/app/services/api_token_service.py` (função `authenticate`)
- Modify: `backend/tests/conftest.py` (fixture `_mock_redis`)
- Create: `backend/tests/test_token_access.py`
- Modify: `backend/tests/test_access_log_guard.py` (teste de código)

**Interfaces:**
- Consumes: `record_event(session, action, entity_type, *, entity_id, workspace_id, detail, changes)` de `app.core.audit`; `set_actor(user_id, kind)` e `current_context()` de `app.core.audit_context`; `get_redis()` de `app.core.redis`.
- Produces: `access_log_service.TOKEN_ACCESS_WINDOW_SECONDS = 3600`; `async access_log_service.record_token_access(session: AsyncSession, row: ApiToken) -> None`. A Tarefa 3 acrescenta mais funções ao mesmo módulo.

- [ ] **Step 1: Create the service with the token part**

`backend/app/services/access_log_service.py`:

```python
"""Keeping the access log: what the trail cannot see for itself, how long it is kept, and the daily anonymising.

Logins, failures, locks and ended sessions are recorded where they happen (`session_service`, `login_guard`).
An API token has no sign-in, so its use is recorded here, when it authenticates.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_event
from app.core.audit_context import current_context, set_actor
from app.core.redis import get_redis
from app.models.api_token import ApiToken

logger = logging.getLogger(__name__)

#: A token used from one address is one access per hour, not one per request.
TOKEN_ACCESS_WINDOW_SECONDS = 3600


async def _first_use_in_window(token_id, ip: str | None) -> bool:
    """True for the first use of this token from this address in the last hour.

    If Redis cannot be asked, the answer is yes: an access is recorded twice rather than not at all,
    and a request never fails because of the log.
    """
    key = f"token_access:{token_id}:{ip or '-'}"
    try:
        redis = await get_redis()
        return bool(await redis.set(key, "1", nx=True, ex=TOKEN_ACCESS_WINDOW_SECONDS))
    except Exception:
        logger.warning("Could not check the token-access window; recording the access anyway", exc_info=True)
        return True


async def record_token_access(session: AsyncSession, row: ApiToken) -> None:
    """Record that `row` authenticated, at most once per hour for each address it comes from."""
    ctx = current_context()
    if not await _first_use_in_window(row.id, ctx.ip):
        return
    set_actor(row.user_id, "api_token")
    await record_event(
        session,
        "token_access",
        "api_token",
        entity_id=row.id,
        workspace_id=row.workspace_id,
        detail=f"api_token:{row.prefix}",
    )
    await session.commit()
```

- [ ] **Step 2: Patch the service's Redis in the autouse fixture**

In `backend/tests/conftest.py`, replace the line `         patch("app.api.two_factor.get_redis", _fake_get_redis):` with:

```python
         patch("app.api.two_factor.get_redis", _fake_get_redis), \
         patch("app.services.access_log_service.get_redis", _fake_get_redis):
```

(The default mock answers `set` with a truthy value, so every token use is "the first" in tests that do not install their own fake.)

- [ ] **Step 3: Write the failing tests**

`backend/tests/test_token_access.py`:

```python
"""Using an API token leaves a mark in the access log: once per token and address per hour."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import patch

from app.core.audit_context import AuditContext, audit_context
from app.models.api_token import ApiToken
from app.models.audit import AuditEvent
from app.models.user import User
from app.services import access_log_service

pytestmark = pytest.mark.asyncio


class FakeRedis:
    """Just enough of Redis for `SET key value NX EX ttl`."""

    def __init__(self) -> None:
        self.keys: set[str] = set()

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys.add(key)
        return True


@pytest.fixture
def fake_redis():
    fake = FakeRedis()

    async def _get():
        return fake

    with patch("app.services.access_log_service.get_redis", _get):
        yield fake


def _bearer(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


async def _make_token(client: AsyncClient, headers: dict) -> dict:
    response = await client.post("/api/api-tokens", json={"name": "Integração", "scopes": ["export.read"], "days": 30}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _events(session: AsyncSession) -> list[AuditEvent]:
    result = await session.execute(
        select(AuditEvent)
        .where(AuditEvent.action == "token_access")
        .order_by(AuditEvent.occurred_at, AuditEvent.id)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def test_the_first_use_is_recorded_with_who_and_which_token(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_headers: dict, fake_redis: FakeRedis
):
    created = await _make_token(client, auth_headers)

    assert (await client.get("/api/accounts", headers=_bearer(created["token"]))).status_code == 200

    [event] = await _events(session)
    row = (await session.execute(select(ApiToken))).scalar_one()
    assert event.actor_kind == "api_token"
    assert event.actor_user_id == test_user.id
    assert event.workspace_id == row.workspace_id
    assert event.entity_type == "api_token" and event.entity_id == created["item"]["id"]
    assert event.detail == f"api_token:{created['item']['prefix']}"


async def test_more_requests_in_the_same_hour_add_nothing(
    client: AsyncClient, session: AsyncSession, auth_headers: dict, fake_redis: FakeRedis
):
    created = await _make_token(client, auth_headers)
    for _ in range(3):
        await client.get("/api/accounts", headers=_bearer(created["token"]))

    assert len(await _events(session)) == 1


async def test_a_new_address_is_recorded_at_once(
    client: AsyncClient, session: AsyncSession, auth_headers: dict, fake_redis: FakeRedis
):
    await _make_token(client, auth_headers)
    row = (await session.execute(select(ApiToken))).scalar_one()

    marker = audit_context.set(AuditContext())
    try:
        for ip in ("203.0.113.1", "203.0.113.1", "203.0.113.2"):
            audit_context.get().ip = ip  # type: ignore[union-attr]
            audit_context.get().user_agent = "curl/8"  # type: ignore[union-attr]
            await access_log_service.record_token_access(session, row)
    finally:
        audit_context.reset(marker)

    assert [event.ip for event in await _events(session)] == ["203.0.113.1", "203.0.113.2"]


async def test_a_token_that_does_not_work_leaves_no_mark(
    client: AsyncClient, session: AsyncSession, test_user: User, fake_redis: FakeRedis
):
    for bad in ("sfn_", "sfn_deadbeef_notarealsecret"):
        assert (await client.get("/api/accounts", headers=_bearer(bad))).status_code == 401

    assert await _events(session) == []


async def test_redis_being_down_does_not_stop_the_request_or_the_record(
    client: AsyncClient, session: AsyncSession, auth_headers: dict
):
    created = await _make_token(client, auth_headers)

    async def _down():
        raise ConnectionError("redis is down")

    with patch("app.services.access_log_service.get_redis", _down):
        response = await client.get("/api/accounts", headers=_bearer(created["token"]))

    assert response.status_code == 200
    assert len(await _events(session)) == 1
```

Append to `backend/tests/test_access_log_guard.py`, inside `class TestTheSqlAgrees`:

```python
    def test_every_access_action_is_recorded_somewhere_in_the_code(self):
        sources = [
            path.read_text(encoding="utf-8")
            for path in (BACKEND / "app").rglob("*.py")
            if path.name != "access_log.py"
        ]
        source = "\n".join(sources)
        for action in ACCESS_ACTIONS:
            assert f'"{action}"' in source, f"{action} is in ACCESS_ACTIONS but nothing records it"
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `TZ=UTC0 .venv/Scripts/python.exe -m pytest tests/test_token_access.py tests/test_access_log_guard.py -q -p no:cacheprovider`
Expected: `test_the_first_use...`, `test_a_new_address...` and `test_redis_being_down...` FAIL (nothing records `token_access` yet), and the guard's new test fails for `token_access`. (`test_more_requests...` fails on `== 1`; the "does not work" test passes already.)

- [ ] **Step 5: Hook it into `authenticate`**

In `backend/app/services/api_token_service.py`, replace the single line `    await touch(session, row)` inside `authenticate` (the one followed by the comment `# From here on the request knows it is a token`; it is the only line with exactly four leading spaces and that text) with:

```python
    await touch(session, row)
    # Imported here: `access_log_service` reads the audit context and Redis, which this module must not load at import.
    from app.services import access_log_service

    await access_log_service.record_token_access(session, row)
```

- [ ] **Step 6: Run the tests and the token/audit suites**

Run: `TZ=UTC0 .venv/Scripts/python.exe -m pytest tests/test_token_access.py tests/test_access_log_guard.py tests/test_api_tokens.py tests/test_audit.py -n 4 -q -p no:cacheprovider`
Expected: all pass. If a test in `test_api_tokens.py` now sees an extra event, its query is too broad: narrow it by `entity_type`; do not weaken the new event.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/access_log_service.py backend/app/services/api_token_service.py backend/tests/conftest.py backend/tests/test_token_access.py backend/tests/test_access_log_guard.py
git commit -m "feat: uso de token de API entra no registro de acessos, 1 por token e IP por hora (D3)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Prazo de guarda e descarte automático

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/services/access_log_service.py`
- Modify: `backend/app/tasks/audit_tasks.py`
- Modify: `backend/app/worker.py`
- Modify: `docker-compose.prod.yml`
- Create: `backend/tests/test_access_log_retention.py`

**Interfaces:**
- Consumes: `add_event` (Task 1); SQL `audit_events_purge_access` (Task 1); `AppSetting(key, value)` de `app.models.app_settings`.
- Produces: `access_log_service.RETENTION_KEY = "access_log_retention_days"`, `PURGE_BATCH = 10_000`; `async retention_days(db) -> int` (sempre entre 183 e 3650); `async set_retention_days(db, days: int) -> int` (levanta `ValueError` fora da faixa); `async purge_expired(db, batch: int = PURGE_BATCH) -> int`; tarefa Celery `app.tasks.audit_tasks.purge_access_log`; `Settings.access_log_retention_days: int = 183`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_access_log_retention.py`:

```python
"""How long access records are kept, and the daily anonymising once that is over."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_settings import AppSetting
from app.models.audit import AuditEvent
from app.services import access_log_service
from tests.access_log_helpers import add_event

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _empty_trail(clean_db):
    yield


async def _set_raw(session: AsyncSession, value: str) -> None:
    session.add(AppSetting(key=access_log_service.RETENTION_KEY, value=value))
    await session.commit()


async def _purged_ids(session: AsyncSession) -> set:
    rows = await session.execute(text("SELECT id FROM audit_events WHERE purged_at IS NOT NULL"))
    return {row.id for row in rows}


class TestTheSetting:
    async def test_it_defaults_to_the_legal_minimum(self, session: AsyncSession):
        assert await access_log_service.retention_days(session) == 183

    async def test_the_environment_supplies_the_default(self, session: AsyncSession):
        with patch("app.services.access_log_service.get_settings", return_value=SimpleNamespace(access_log_retention_days=400)):
            assert await access_log_service.retention_days(session) == 400

    async def test_the_saved_value_wins(self, session: AsyncSession):
        await access_log_service.set_retention_days(session, 365)
        assert await access_log_service.retention_days(session) == 365

    async def test_a_value_saved_out_of_range_is_held_inside_it(self, session: AsyncSession):
        await _set_raw(session, "10")
        assert await access_log_service.retention_days(session) == 183
        await session.execute(text("UPDATE app_settings SET value = '99999'"))
        await session.commit()
        assert await access_log_service.retention_days(session) == 3650

    async def test_garbage_falls_back_to_the_default(self, session: AsyncSession):
        await _set_raw(session, "muito tempo")
        assert await access_log_service.retention_days(session) == 183

    async def test_saving_outside_the_range_is_refused(self, session: AsyncSession):
        for days in (0, 182, 3651):
            with pytest.raises(ValueError):
                await access_log_service.set_retention_days(session, days)

    async def test_changing_it_is_in_the_audit_trail(self, session: AsyncSession):
        await access_log_service.set_retention_days(session, 365)
        await access_log_service.set_retention_days(session, 400)

        events = (
            await session.execute(
                select(AuditEvent)
                .where(AuditEvent.entity_type == "app_settings", AuditEvent.entity_id == access_log_service.RETENTION_KEY)
                .order_by(AuditEvent.occurred_at)
                .execution_options(populate_existing=True)
            )
        ).scalars().all()
        assert [event.action for event in events] == ["create", "update"]
        assert events[1].changes == {"value": ["365", "400"]}


class TestThePurge:
    async def test_it_anonymises_what_the_period_has_passed_and_says_so(self, session: AsyncSession):
        old = await add_event(session, age_days=400)
        middle = await add_event(session, action="login_failed", age_days=200)
        fresh = await add_event(session, age_days=100)
        await access_log_service.set_retention_days(session, 300)

        assert await access_log_service.purge_expired(session) == 1
        assert await _purged_ids(session) == {old}

        await access_log_service.set_retention_days(session, 183)
        assert await access_log_service.purge_expired(session) == 1
        assert await _purged_ids(session) == {old, middle}
        assert fresh not in await _purged_ids(session)

        notes = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "access_log_purged").order_by(AuditEvent.occurred_at)
            )
        ).scalars().all()
        assert [note.detail for note in notes] == ["1 events, 300 days", "1 events, 183 days"]
        assert {note.actor_kind for note in notes} == {"system"}

    async def test_with_nothing_due_it_says_nothing(self, session: AsyncSession):
        await add_event(session, age_days=10)

        assert await access_log_service.purge_expired(session) == 0

        assert (await session.execute(select(AuditEvent).where(AuditEvent.action == "access_log_purged"))).first() is None

    async def test_it_goes_on_until_everything_due_is_done(self, session: AsyncSession):
        for _ in range(5):
            await add_event(session, age_days=400)

        assert await access_log_service.purge_expired(session, batch=2) == 5
        assert len(await _purged_ids(session)) == 5


def test_the_daily_job_is_scheduled():
    from app.tasks import audit_tasks
    from app.worker import celery_app

    entry = celery_app.conf.beat_schedule["purge-access-log-daily"]
    assert entry["task"] == audit_tasks.purge_access_log.name == "app.tasks.audit_tasks.purge_access_log"
    assert entry["schedule"] == 60 * 60 * 24
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TZ=UTC0 .venv/Scripts/python.exe -m pytest tests/test_access_log_retention.py -q -p no:cacheprovider`
Expected: FAIL (`retention_days`, `RETENTION_KEY`, `purge_expired`, the task and the schedule do not exist).

- [ ] **Step 3: Add the setting**

In `backend/app/core/config.py`, replace the line `    login_lock_minutes: int = 15` with:

```python
    login_lock_minutes: int = 15

    # How long access records (sign-ins, failures, locks, token use) are kept before they are anonymised.
    # The administrator can change it in the panel; this is what applies until they do. 183 to 3650 days.
    access_log_retention_days: int = 183
```

In `docker-compose.prod.yml` (LF file), replace the line `  LOGIN_LOCK_MINUTES: ${LOGIN_LOCK_MINUTES:-15}` with:

```yaml
  LOGIN_LOCK_MINUTES: ${LOGIN_LOCK_MINUTES:-15}
  # How long access records are kept before they are anonymised (183 to 3650 days; the panel can override it).
  ACCESS_LOG_RETENTION_DAYS: ${ACCESS_LOG_RETENTION_DAYS:-183}
```

- [ ] **Step 4: Add the retention and purge functions**

In `backend/app/services/access_log_service.py`, replace the import line `from sqlalchemy.ext.asyncio import AsyncSession` with:

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
```

replace `from app.core.audit import record_event` with:

```python
from app.core.access_log import ACCESS_MAX_RETENTION_DAYS, ACCESS_MIN_RETENTION_DAYS
from app.core.audit import record_event
```

replace `from app.core.redis import get_redis` with:

```python
from app.core.config import get_settings
from app.core.redis import get_redis
```

replace `from app.models.api_token import ApiToken` with:

```python
from app.models.api_token import ApiToken
from app.models.app_settings import AppSetting
```

replace the line `TOKEN_ACCESS_WINDOW_SECONDS = 3600` with:

```python
TOKEN_ACCESS_WINDOW_SECONDS = 3600

RETENTION_KEY = "access_log_retention_days"
#: Rows anonymised per statement, so one run never holds a long lock.
PURGE_BATCH = 10_000
```

and append at the end of the file:

```python


async def retention_days(db: AsyncSession) -> int:
    """How long access records are kept: the saved value, else the environment's, held to 183..3650.

    A value saved by some other route (the generic settings endpoint) is clamped here, and the database
    refuses to anonymise anything under 183 days whatever this returns.
    """
    row = await db.get(AppSetting, RETENTION_KEY)
    for candidate in (row.value if row is not None else None, get_settings().access_log_retention_days):
        try:
            days = int(candidate)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        return max(ACCESS_MIN_RETENTION_DAYS, min(days, ACCESS_MAX_RETENTION_DAYS))
    return ACCESS_MIN_RETENTION_DAYS


async def set_retention_days(db: AsyncSession, days: int) -> int:
    """Save the retention period. The change is audited like every other setting."""
    if not ACCESS_MIN_RETENTION_DAYS <= days <= ACCESS_MAX_RETENTION_DAYS:
        raise ValueError(f"The retention period is between {ACCESS_MIN_RETENTION_DAYS} and {ACCESS_MAX_RETENTION_DAYS} days")
    row = await db.get(AppSetting, RETENTION_KEY)
    if row is None:
        db.add(AppSetting(key=RETENTION_KEY, value=str(days)))
    else:
        row.value = str(days)
    await db.commit()
    return days


async def purge_expired(db: AsyncSession, batch: int = PURGE_BATCH) -> int:
    """Anonymise every access event older than the retention period. Returns how many.

    Runs in batches, each in its own transaction. Something was done, so the trail says so (a system event).
    """
    days = await retention_days(db)
    total = 0
    while True:
        done = (
            await db.execute(text("SELECT audit_events_purge_access(:days, :batch)"), {"days": days, "batch": batch})
        ).scalar_one()
        await db.commit()
        total += done
        if done < batch:
            break
    if total:
        await record_event(db, "access_log_purged", "audit_events", detail=f"{total} events, {days} days")
        await db.commit()
    return total
```

- [ ] **Step 5: Add the Celery task and its schedule**

In `backend/app/tasks/audit_tasks.py`, replace the line `from app.core.config import get_settings` with:

```python
from app.core.config import get_settings
from app.services import access_log_service
```

and append at the end of the file:

```python


async def _purge() -> int:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession)() as session:
            return await access_log_service.purge_expired(session)
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.audit_tasks.purge_access_log")
def purge_access_log() -> int:
    """Anonymise the access records whose retention period is over."""
    purged = asyncio.run(_purge())
    if purged:
        logger.info("Access log: anonymised %d events", purged)
    return purged
```

In `backend/app/worker.py`, replace the line `    "auto-apply-reconciliation-hourly": {` with:

```python
    "purge-access-log-daily": {
        "task": "app.tasks.audit_tasks.purge_access_log",
        # Anonymises access records older than the retention period (`access_log_retention_days`).
        "schedule": 60 * 60 * 24,
    },
    "auto-apply-reconciliation-hourly": {
```

- [ ] **Step 6: Run the tests, ruff and ty**

Run: `TZ=UTC0 .venv/Scripts/python.exe -m pytest tests/test_access_log_retention.py tests/test_access_log_guard.py tests/test_token_access.py -n 4 -q -p no:cacheprovider` then `.venv/Scripts/ruff.exe check .` and `.venv/Scripts/ty.exe check .`
Expected: all pass; ruff and ty report `All checks passed!`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/config.py backend/app/services/access_log_service.py backend/app/tasks/audit_tasks.py backend/app/worker.py backend/tests/test_access_log_retention.py docker-compose.prod.yml
git commit -m "feat: prazo de guarda configurável e descarte diário por anonimização (D3)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 4: Rotas de consulta, exportação, histórico próprio e prazo

**Files:**
- Create: `backend/app/api/access_log.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_write_permission_coverage.py`
- Create: `backend/tests/test_access_log_api.py`

**Interfaces:**
- Consumes: de `app.api.audit`: `AuditPage`, `EXPORT_LIMIT`, `_csv(rows)`, `_filters(*, workspace_id, date_from, date_to, actor_user_id, entity_type, entity_id, action)`, `_page(session, conditions, page, limit)`, `_select_with_actor()`; `access_log_service.retention_days/set_retention_days` (Task 3); `add_event` (Task 1).
- Produces (HTTP): `GET /api/admin/access-log`, `GET /api/admin/access-log/export`, `GET|PUT /api/admin/access-log/retention`, `GET /api/auth/access-history`. Formas: retenção `{"days": int, "minimum": 183, "maximum": 3650}`; histórico `{"items": [{"id","occurred_at","action","actor_kind","detail","ip","user_agent"}], "total","page","limit"}`; a lista do administrador usa `AuditPage`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_access_log_api.py`:

```python
"""The access log: the administrator's view of the instance, each person's own history, and the retention setting."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent
from app.models.user import User
from tests.access_log_helpers import add_event

pytestmark = pytest.mark.asyncio

LOG = "/api/admin/access-log"
HISTORY = "/api/auth/access-history"


@pytest_asyncio.fixture(autouse=True)
async def _empty_trail(clean_db):
    yield


class TestTheAdministratorsView:
    async def test_it_lists_access_events_newest_first_and_only_those(
        self, client: AsyncClient, session: AsyncSession, test_user: User, admin_auth_headers: dict
    ):
        await add_event(session, action="login", age_days=3, actor_user_id=test_user.id)
        await add_event(session, action="login_failed", age_days=2, actor_user_id=None, detail="unknown_user", ip="203.0.113.5")
        await add_event(session, action="update", entity_type="accounts", age_days=1)

        response = await client.get(LOG, headers=admin_auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert [item["action"] for item in body["items"]] == ["login_failed", "login"]
        assert body["items"][1]["actor_email"] == "test@example.com"
        assert body["items"][0]["actor_email"] is None and body["items"][0]["ip"] == "203.0.113.5"

    async def test_it_filters_by_action_ip_person_and_period(
        self, client: AsyncClient, session: AsyncSession, test_user: User, admin_auth_headers: dict
    ):
        await add_event(session, action="login", age_days=10, actor_user_id=test_user.id, ip="198.51.100.1")
        await add_event(session, action="login_failed", age_days=1, ip="203.0.113.9")

        async def count(**params) -> int:
            return (await client.get(LOG, params=params, headers=admin_auth_headers)).json()["total"]

        assert await count(action="login_failed") == 1
        assert await count(ip="198.51.100.1") == 1
        assert await count(actor_user_id=str(test_user.id)) == 1
        since = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        assert await count(**{"from": since}) == 1
        assert await count(**{"from": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}) == 0

    async def test_an_action_outside_the_set_is_refused(self, client: AsyncClient, admin_auth_headers: dict):
        assert (await client.get(LOG, params={"action": "update"}, headers=admin_auth_headers)).status_code == 422
        assert (await client.get(LOG, params={"limit": 201}, headers=admin_auth_headers)).status_code == 422

    async def test_anonymised_events_are_left_out(
        self, client: AsyncClient, session: AsyncSession, admin_auth_headers: dict
    ):
        await add_event(session, age_days=400)
        await add_event(session, age_days=1)
        await session.execute(text("SELECT audit_events_purge_access(183, 100)"))
        await session.commit()

        assert (await client.get(LOG, headers=admin_auth_headers)).json()["total"] == 1

    async def test_the_csv_carries_the_hashes_and_the_same_filter(
        self, client: AsyncClient, session: AsyncSession, admin_auth_headers: dict
    ):
        await add_event(session, action="login", ip="198.51.100.1", seal_it=False)
        await add_event(session, action="login_failed", ip="203.0.113.9", seal_it=False)

        response = await client.get(f"{LOG}/export", params={"action": "login_failed"}, headers=admin_auth_headers)

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "registros-de-acesso.csv" in response.headers["content-disposition"]
        assert response.text.startswith("﻿")
        lines = response.text.strip().splitlines()
        assert len(lines) == 2 and "203.0.113.9" in lines[1] and "198.51.100.1" not in response.text
        hash_value = lines[1].split(";")[-1]
        assert len(hash_value) == 64, "sealed before it was written"

    async def test_only_an_administrator_may_read_it(self, client: AsyncClient, auth_headers: dict):
        for path in (LOG, f"{LOG}/export", f"{LOG}/retention"):
            assert (await client.get(path, headers=auth_headers)).status_code == 403, path
        assert (await client.put(f"{LOG}/retention", json={"days": 400}, headers=auth_headers)).status_code == 403
        assert (await client.get(LOG)).status_code == 401

    async def test_reading_it_records_nothing(
        self, client: AsyncClient, session: AsyncSession, admin_auth_headers: dict
    ):
        await add_event(session)
        before = (await session.execute(select(AuditEvent.id))).scalars().all()
        await client.get(LOG, headers=admin_auth_headers)
        await client.get(f"{LOG}/export", headers=admin_auth_headers)
        session.expire_all()
        assert set((await session.execute(select(AuditEvent.id))).scalars().all()) == set(before)


class TestARetentionSetting:
    async def test_it_reads_and_changes_within_the_limits(self, client: AsyncClient, admin_auth_headers: dict):
        assert (await client.get(f"{LOG}/retention", headers=admin_auth_headers)).json() == {
            "days": 183, "minimum": 183, "maximum": 3650,
        }

        saved = await client.put(f"{LOG}/retention", json={"days": 400}, headers=admin_auth_headers)
        assert saved.status_code == 200 and saved.json()["days"] == 400
        assert (await client.get(f"{LOG}/retention", headers=admin_auth_headers)).json()["days"] == 400

    async def test_it_refuses_a_period_outside_the_limits(self, client: AsyncClient, admin_auth_headers: dict):
        for days in (0, 100, 182, 3651):
            response = await client.put(f"{LOG}/retention", json={"days": days}, headers=admin_auth_headers)
            assert response.status_code == 422, days


class TestEachPersonsOwnHistory:
    async def test_a_person_sees_only_their_own_events_and_not_the_hash(
        self, client: AsyncClient, session: AsyncSession, test_user: User, auth_headers: dict
    ):
        other = uuid.uuid4()
        await add_event(session, action="login", age_days=2, actor_user_id=test_user.id, ip="198.51.100.1")
        await add_event(session, action="login_failed", age_days=1, actor_user_id=test_user.id, detail="bad_password")
        await add_event(session, action="login", actor_user_id=other)
        await add_event(session, action="update", entity_type="accounts", actor_user_id=test_user.id)

        response = await client.get(HISTORY, params={"actor_user_id": str(other)}, headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert [item["action"] for item in body["items"]] == ["login_failed", "login"]
        assert body["items"][0]["detail"] == "bad_password"
        assert set(body["items"][0]) == {"id", "occurred_at", "action", "actor_kind", "detail", "ip", "user_agent"}

    async def test_it_pages_and_leaves_out_anonymised_events(
        self, client: AsyncClient, session: AsyncSession, test_user: User, auth_headers: dict
    ):
        await add_event(session, age_days=400, actor_user_id=test_user.id)
        for days in (3, 2, 1):
            await add_event(session, age_days=days, actor_user_id=test_user.id)
        await session.execute(text("SELECT audit_events_purge_access(183, 100)"))
        await session.commit()

        first = (await client.get(HISTORY, params={"limit": 2}, headers=auth_headers)).json()
        second = (await client.get(HISTORY, params={"limit": 2, "page": 2}, headers=auth_headers)).json()

        assert first["total"] == 3 and len(first["items"]) == 2 and len(second["items"]) == 1
        assert (await client.get(HISTORY, params={"limit": 101}, headers=auth_headers)).status_code == 422

    async def test_it_needs_a_signed_in_person_and_refuses_a_token(
        self, client: AsyncClient, test_user: User, auth_headers: dict
    ):
        assert (await client.get(HISTORY)).status_code == 401
        made = await client.post(
            "/api/api-tokens", json={"name": "x", "scopes": ["export.read"], "days": 30}, headers=auth_headers
        )
        secret = made.json()["token"]
        refused = await client.get(HISTORY, headers={"Authorization": f"Bearer {secret}"})
        assert refused.status_code == 403 and refused.json()["detail"] == "API_TOKEN_NOT_ALLOWED"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `TZ=UTC0 .venv/Scripts/python.exe -m pytest tests/test_access_log_api.py -q -p no:cacheprovider`
Expected: FAIL with 404 responses (the routes do not exist).

- [ ] **Step 3: Create the router**

`backend/app/api/access_log.py`:

```python
"""Reading the access log, and setting how long it is kept.

The administrator sees every access to the instance; each person sees their own. Both read
`audit_events` through the fixed set of access actions (`core/access_log.py`) and skip rows already
anonymised: those no longer say who or from where. Reading never writes to the trail.
"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# The audit module's own query helpers: the access log is the same rows, filtered, in the same formats.
from app.api.audit import EXPORT_LIMIT, AuditPage, _csv, _filters, _page, _select_with_actor
from app.core.access_log import ACCESS_ACTIONS, ACCESS_MAX_RETENTION_DAYS, ACCESS_MIN_RETENTION_DAYS
from app.core.audit import seal
from app.core.auth import current_active_user, current_superuser
from app.core.database import get_async_session
from app.models.audit import AuditEvent
from app.models.user import User
from app.services import access_log_service

router = APIRouter(tags=["access-log"])


class RetentionRead(BaseModel):
    days: int
    minimum: int = ACCESS_MIN_RETENTION_DAYS
    maximum: int = ACCESS_MAX_RETENTION_DAYS


class RetentionWrite(BaseModel):
    days: int = Field(ge=ACCESS_MIN_RETENTION_DAYS, le=ACCESS_MAX_RETENTION_DAYS)


class AccessHistoryItem(BaseModel):
    """What a person is shown about their own access: no hash, no one else's details."""

    id: uuid.UUID
    occurred_at: datetime
    action: str
    actor_kind: str
    detail: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None


class AccessHistoryPage(BaseModel):
    items: list[AccessHistoryItem]
    total: int
    page: int
    limit: int


def _conditions(
    *,
    date_from: datetime | None,
    date_to: datetime | None,
    actor_user_id: uuid.UUID | None,
    ip: str | None,
    action: str | None,
) -> list:
    if action is not None and action not in ACCESS_ACTIONS:
        raise HTTPException(status_code=422, detail="UNKNOWN_ACCESS_ACTION")
    conditions = _filters(
        workspace_id=None, date_from=date_from, date_to=date_to, actor_user_id=actor_user_id,
        entity_type=None, entity_id=None, action=action,
    )
    conditions.append(AuditEvent.action.in_(ACCESS_ACTIONS))
    conditions.append(AuditEvent.purged_at.is_(None))
    if ip:
        conditions.append(AuditEvent.ip == ip)
    return conditions


# --- the whole instance (administrator) --------------------------------------------------


@router.get("/api/admin/access-log", response_model=AuditPage)
async def list_access_log(
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
    actor_user_id: Optional[uuid.UUID] = None,
    ip: Optional[str] = None,
    action: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    conditions = _conditions(date_from=date_from, date_to=date_to, actor_user_id=actor_user_id, ip=ip, action=action)
    return await _page(session, conditions, page, limit)


@router.get("/api/admin/access-log/export")
async def export_access_log(
    date_from: Optional[datetime] = Query(None, alias="from"),
    date_to: Optional[datetime] = Query(None, alias="to"),
    actor_user_id: Optional[uuid.UUID] = None,
    ip: Optional[str] = None,
    action: Optional[str] = None,
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    conditions = _conditions(date_from=date_from, date_to=date_to, actor_user_id=actor_user_id, ip=ip, action=action)
    await seal(session)  # so the file carries the hashes
    rows = (
        await session.execute(
            _select_with_actor().where(*conditions).order_by(AuditEvent.occurred_at.asc(), AuditEvent.id.asc()).limit(EXPORT_LIMIT)
        )
    ).all()
    return StreamingResponse(
        iter([_csv([(event, email) for event, email in rows])]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="registros-de-acesso.csv"'},
    )


@router.get("/api/admin/access-log/retention", response_model=RetentionRead)
async def get_retention(
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    return RetentionRead(days=await access_log_service.retention_days(session))


@router.put("/api/admin/access-log/retention", response_model=RetentionRead)
async def put_retention(
    body: RetentionWrite,
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    return RetentionRead(days=await access_log_service.set_retention_days(session, body.days))


# --- a person's own accesses ---------------------------------------------------------------


@router.get("/api/auth/access-history", response_model=AccessHistoryPage)
async def my_access_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """The signed-in person's own accesses. The person comes from the session, never from the request."""
    conditions = [
        AuditEvent.action.in_(ACCESS_ACTIONS),
        AuditEvent.purged_at.is_(None),
        AuditEvent.actor_user_id == user.id,
    ]
    total = (await session.execute(select(func.count()).select_from(AuditEvent).where(*conditions))).scalar_one()
    rows = (
        await session.execute(
            select(AuditEvent)
            .where(*conditions)
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).scalars().all()
    items = [AccessHistoryItem.model_validate(row, from_attributes=True) for row in rows]
    return AccessHistoryPage(items=items, total=total, page=page, limit=limit)
```

- [ ] **Step 4: Register the router**

In `backend/app/main.py`, replace the line `from app.api.audit import router as audit_router` with:

```python
from app.api.audit import router as audit_router
from app.api.access_log import router as access_log_router
```

and replace the line `app.include_router(audit_router)` with:

```python
app.include_router(audit_router)
app.include_router(access_log_router)
```

- [ ] **Step 5: Add the write route to the permission allowlist**

In `backend/tests/test_write_permission_coverage.py`, replace the line `    ("POST", "/api/admin/users/{user_id}/unlock"): "superuser-gated instance administration",` with itself plus:

```python
    ("POST", "/api/admin/users/{user_id}/unlock"): "superuser-gated instance administration",
    ("PUT", "/api/admin/access-log/retention"): "superuser-gated instance administration",
```

- [ ] **Step 6: Run the tests, the coverage test, ruff and ty**

Run: `TZ=UTC0 .venv/Scripts/python.exe -m pytest tests/test_access_log_api.py tests/test_write_permission_coverage.py tests/test_api_tokens.py -n 4 -q -p no:cacheprovider`, then `.venv/Scripts/ruff.exe check .` and `.venv/Scripts/ty.exe check .`
Expected: all pass; `All checks passed!` twice. If `ty` objects to importing the underscore helpers from `app.api.audit`, keep the import and add `# noqa: PLC2701` only if ruff asks for it.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/access_log.py backend/app/main.py backend/tests/test_access_log_api.py backend/tests/test_write_permission_coverage.py
git commit -m "feat: rotas do registro de acessos, do histórico próprio e do prazo de guarda (D3)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 5: Página "Registros de acesso" (frontend)

**Files:**
- Modify: `frontend/src/locales/en.json`, `es.json`, `pt-BR.json` (via script)
- Modify: `frontend/src/types/index.ts`, `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/access-log.ts`, `frontend/src/lib/access-log.test.ts`
- Create: `frontend/src/pages/admin/access-log.tsx`, `frontend/src/pages/admin/access-log.test.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes (HTTP, Task 4): `GET /admin/access-log` (forma `AuditPage`), `GET /admin/access-log/export` (CSV), `GET|PUT /admin/access-log/retention`, `GET /auth/access-history`. `admin.listUsers({ limit })` já existe e devolve `{ items: AdminUser[], total }`.
- Produces: tipos `AccessLogFilters`, `AccessHistoryItem`, `AccessHistoryPage`, `AccessRetention`; `accessLog.{list, exportCsv, retention, setRetention}` e `auth.accessHistory(limit?)` em `@/lib/api`; `ACCESS_ACTIONS`, `accessAction(t, action)`, `accessReason(t, action, detail)` em `@/lib/access-log`; chaves i18n `accessLog.*`, `admin.accessRetention.*`, `auth.recentAccess.*` (usadas também na Task 6).

- [ ] **Step 1: Add the texts in the three languages**

Write this script to `C:\Users\gusta\AppData\Local\Temp\claude\d--Projeto-Finance\52652492-91ef-4104-96ad-0b5302c8eda6\scratchpad\add_locale_keys.py` (do not commit it), then run it with `python <that path>`. It rewrites each locale file keeping its line endings.

```python
import json

ROOT = r"D:\Projeto Finance\FinanceBR-Interprise\frontend\src\locales"

NEW = {
    "en": {
        "accessLog": {
            "section": "Administration",
            "title": "Access log",
            "description": "Every sign-in, failed attempt, lock, ended session and API-token use. Kept for {{days}} days, without any way to edit or erase it; after that the records are anonymized (person, address and device are removed).",
            "from": "From",
            "to": "To",
            "person": "Person",
            "ip": "IP address",
            "action": "Event",
            "all": "All",
            "filter": "Filter",
            "export": "Export CSV",
            "exportFailed": "Could not export the log.",
            "when": "When",
            "who": "Person",
            "device": "Device",
            "empty": "No access records for these filters.",
            "loadFailed": "Could not load the access log.",
            "deletedUser": "Removed account",
            "apiToken": "API token",
            "previous": "Previous",
            "next": "Next",
            "pageOf": "Page {{page}} of {{pages}}",
            "actions": {
                "login": "Signed in",
                "login_failed": "Failed sign-in",
                "login_blocked": "Sign-in blocked (locked account)",
                "account_locked": "Account locked",
                "account_unlocked": "Account unlocked",
                "session_revoked": "Session ended",
                "token_access": "API token used",
            },
            "reasons": {
                "password": "password",
                "2fa": "authenticator code",
                "passkey": "passkey",
                "oidc": "company sign-in",
                "setup": "first setup",
                "bad_password": "wrong password",
                "bad_2fa_code": "wrong authenticator code",
                "inactive": "disabled account",
                "unknown_user": "unknown e-mail",
                "account_locked": "account locked",
                "logout": "signed out",
                "revoked_by_user": "ended from another device",
                "password_changed": "password changed",
                "account_disabled": "account disabled",
                "refresh_reuse": "suspected token theft",
                "admin": "by an administrator",
                "cli": "by the server command",
                "password_reset": "by password reset",
                "token": "token {{prefix}}",
            },
        },
        "accessRetention": {
            "title": "Access log retention",
            "description": "How long sign-in and access records are kept before they are anonymized. The legal minimum is 6 months ({{min}} days).",
            "days": "Days kept",
            "hint": "Between {{min}} and {{max}} days.",
            "shorter": "Shortening the period anonymizes the older records the next time the daily job runs. This cannot be undone.",
            "invalid": "Enter a whole number between {{min}} and {{max}}.",
            "save": "Save",
            "saved": "Retention period updated.",
            "viewLog": "View the access log",
        },
        "recentAccess": {"title": "Recent access", "empty": "No access recorded yet."},
    },
    "pt-BR": {
        "accessLog": {
            "section": "Administração",
            "title": "Registros de acesso",
            "description": "Cada login, tentativa falha, bloqueio, sessão encerrada e uso de token de API. Guardados por {{days}} dias, sem possibilidade de edição ou remoção; depois disso, os registros são anonimizados (pessoa, endereço e dispositivo são removidos).",
            "from": "De",
            "to": "Até",
            "person": "Pessoa",
            "ip": "Endereço IP",
            "action": "Evento",
            "all": "Todos",
            "filter": "Filtrar",
            "export": "Exportar CSV",
            "exportFailed": "Não foi possível exportar o registro.",
            "when": "Quando",
            "who": "Pessoa",
            "device": "Dispositivo",
            "empty": "Nenhum registro de acesso para estes filtros.",
            "loadFailed": "Não foi possível carregar os registros de acesso.",
            "deletedUser": "Conta removida",
            "apiToken": "Token de API",
            "previous": "Anterior",
            "next": "Próxima",
            "pageOf": "Página {{page}} de {{pages}}",
            "actions": {
                "login": "Entrou",
                "login_failed": "Falha de login",
                "login_blocked": "Login bloqueado (conta travada)",
                "account_locked": "Conta bloqueada",
                "account_unlocked": "Conta desbloqueada",
                "session_revoked": "Sessão encerrada",
                "token_access": "Token de API usado",
            },
            "reasons": {
                "password": "senha",
                "2fa": "código do aplicativo",
                "passkey": "chave de acesso",
                "oidc": "login da empresa",
                "setup": "primeira configuração",
                "bad_password": "senha errada",
                "bad_2fa_code": "código do aplicativo errado",
                "inactive": "conta desativada",
                "unknown_user": "e-mail desconhecido",
                "account_locked": "conta bloqueada",
                "logout": "saiu",
                "revoked_by_user": "encerrada em outro dispositivo",
                "password_changed": "senha alterada",
                "account_disabled": "conta desativada",
                "refresh_reuse": "suspeita de token roubado",
                "admin": "por um administrador",
                "cli": "pelo comando do servidor",
                "password_reset": "por redefinição de senha",
                "token": "token {{prefix}}",
            },
        },
        "accessRetention": {
            "title": "Prazo de guarda dos registros de acesso",
            "description": "Por quanto tempo os registros de login e de acesso são guardados antes de serem anonimizados. O mínimo legal é de 6 meses ({{min}} dias).",
            "days": "Dias de guarda",
            "hint": "Entre {{min}} e {{max}} dias.",
            "shorter": "Reduzir o prazo anonimiza os registros mais antigos na próxima execução da tarefa diária. Isso não pode ser desfeito.",
            "invalid": "Informe um número inteiro entre {{min}} e {{max}}.",
            "save": "Salvar",
            "saved": "Prazo de guarda atualizado.",
            "viewLog": "Ver os registros de acesso",
        },
        "recentAccess": {"title": "Acessos recentes", "empty": "Nenhum acesso registrado ainda."},
    },
    "es": {
        "accessLog": {
            "section": "Administración",
            "title": "Registros de acceso",
            "description": "Cada inicio de sesión, intento fallido, bloqueo, sesión cerrada y uso de token de API. Se guardan {{days}} días, sin posibilidad de editarlos ni borrarlos; después se anonimizan (se eliminan la persona, la dirección y el dispositivo).",
            "from": "Desde",
            "to": "Hasta",
            "person": "Persona",
            "ip": "Dirección IP",
            "action": "Evento",
            "all": "Todos",
            "filter": "Filtrar",
            "export": "Exportar CSV",
            "exportFailed": "No se pudo exportar el registro.",
            "when": "Cuándo",
            "who": "Persona",
            "device": "Dispositivo",
            "empty": "Ningún registro de acceso para estos filtros.",
            "loadFailed": "No se pudieron cargar los registros de acceso.",
            "deletedUser": "Cuenta eliminada",
            "apiToken": "Token de API",
            "previous": "Anterior",
            "next": "Siguiente",
            "pageOf": "Página {{page}} de {{pages}}",
            "actions": {
                "login": "Inició sesión",
                "login_failed": "Inicio de sesión fallido",
                "login_blocked": "Inicio bloqueado (cuenta bloqueada)",
                "account_locked": "Cuenta bloqueada",
                "account_unlocked": "Cuenta desbloqueada",
                "session_revoked": "Sesión cerrada",
                "token_access": "Token de API usado",
            },
            "reasons": {
                "password": "contraseña",
                "2fa": "código de la aplicación",
                "passkey": "passkey",
                "oidc": "inicio de sesión de la empresa",
                "setup": "primera configuración",
                "bad_password": "contraseña incorrecta",
                "bad_2fa_code": "código de la aplicación incorrecto",
                "inactive": "cuenta desactivada",
                "unknown_user": "correo desconocido",
                "account_locked": "cuenta bloqueada",
                "logout": "cerró sesión",
                "revoked_by_user": "cerrada desde otro dispositivo",
                "password_changed": "contraseña cambiada",
                "account_disabled": "cuenta desactivada",
                "refresh_reuse": "sospecha de token robado",
                "admin": "por un administrador",
                "cli": "por el comando del servidor",
                "password_reset": "por restablecimiento de contraseña",
                "token": "token {{prefix}}",
            },
        },
        "accessRetention": {
            "title": "Plazo de conservación de los registros de acceso",
            "description": "Cuánto tiempo se guardan los registros de inicio de sesión y de acceso antes de anonimizarse. El mínimo legal es de 6 meses ({{min}} días).",
            "days": "Días de conservación",
            "hint": "Entre {{min}} y {{max}} días.",
            "shorter": "Reducir el plazo anonimiza los registros más antiguos la próxima vez que se ejecute la tarea diaria. No se puede deshacer.",
            "invalid": "Introduce un número entero entre {{min}} y {{max}}.",
            "save": "Guardar",
            "saved": "Plazo de conservación actualizado.",
            "viewLog": "Ver los registros de acceso",
        },
        "recentAccess": {"title": "Accesos recientes", "empty": "Aún no hay accesos registrados."},
    },
}

for lang, blocks in NEW.items():
    path = rf"{ROOT}\{lang}.json"
    raw = open(path, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    data = json.loads(raw)
    data["accessLog"] = blocks["accessLog"]
    data["admin"]["accessRetention"] = blocks["accessRetention"]
    data["auth"]["recentAccess"] = blocks["recentAccess"]
    out = json.dumps(data, ensure_ascii=False, indent=2).replace("\n", nl) + (nl if raw.endswith("\n") else "")
    open(path, "w", encoding="utf-8", newline="").write(out)
    print("ok", lang)
```

Run `npm run i18n:check -- --strict` in `frontend/`. Expected: passes (all three files have the same keys). `git diff --stat frontend/src/locales` must show only additions.

- [ ] **Step 2: Add the types and the API client**

In `frontend/src/types/index.ts`, replace the line `export interface AuditVerification {` with:

```ts
/** Filters of the administrator's access log (`GET /admin/access-log`; the rows have the `AuditEvent` shape). */
export interface AccessLogFilters {
  from?: string
  to?: string
  actor_user_id?: string
  ip?: string
  action?: string
}

/** One of a person's own accesses (`GET /auth/access-history`): no hash, nothing about anyone else. */
export interface AccessHistoryItem {
  id: string
  occurred_at: string
  action: string
  actor_kind: 'user' | 'api_token' | 'system'
  detail: string | null
  ip: string | null
  user_agent: string | null
}

export interface AccessHistoryPage {
  items: AccessHistoryItem[]
  total: number
  page: number
  limit: number
}

/** How long access records are kept before they are anonymized (`GET /admin/access-log/retention`). */
export interface AccessRetention {
  days: number
  minimum: number
  maximum: number
}

export interface AuditVerification {
```

In `frontend/src/lib/api.ts`:

1. Replace the line `} from '@/types'` (the end of the big `import type {` block near the top) with:

```ts
  AccessHistoryPage,
  AccessLogFilters,
  AccessRetention,
} from '@/types'
```

2. Replace the line `// Reconciliation: accept the suggestions above the workspace's confidence bar now.` with:

```ts
// Administrator: who got into the instance (or tried), and how long that is kept.
export const accessLog = {
  list: async (filters: AccessLogFilters, page: number, limit = 50): Promise<AuditPage> => {
    const { data } = await api.get('/admin/access-log', { params: { ...filters, page, limit } })
    return data
  },
  exportCsv: async (filters: AccessLogFilters): Promise<void> => {
    const { data } = await api.get('/admin/access-log/export', { params: filters, responseType: 'blob' })
    const url = URL.createObjectURL(new Blob([data], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'registros-de-acesso.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
  retention: async (): Promise<AccessRetention> => {
    const { data } = await api.get('/admin/access-log/retention')
    return data
  },
  setRetention: async (days: number): Promise<AccessRetention> => {
    const { data } = await api.put('/admin/access-log/retention', { days })
    return data
  },
}

// Reconciliation: accept the suggestions above the workspace's confidence bar now.
```

3. Inside the `auth` object, replace the line `  updateMe: async (updates: Partial<User>): Promise<User> => {` with:

```ts
  /** The signed-in person's own recent accesses (sign-ins, failures, ended sessions, their tokens' use). */
  accessHistory: async (limit = 20): Promise<AccessHistoryPage> => {
    const { data } = await api.get('/auth/access-history', { params: { limit } })
    return data
  },
  updateMe: async (updates: Partial<User>): Promise<User> => {
```

- [ ] **Step 3: Write the failing test for the label helper**

`frontend/src/lib/access-log.test.ts`:

```ts
import { describe, expect, it } from 'vitest'

import { ACCESS_ACTIONS, accessAction, accessReason } from '@/lib/access-log'
import { t } from '@/test/utils'

describe('access log labels', () => {
  it('names every action in the set', () => {
    for (const action of ACCESS_ACTIONS) {
      expect(accessAction(t, action)).toBe(t(`accessLog.actions.${action}`))
      expect(accessAction(t, action)).not.toContain('accessLog.')
    }
  })

  it('explains why a sign-in failed', () => {
    expect(accessReason(t, 'login_failed', 'bad_password')).toBe(t('accessLog.reasons.bad_password'))
  })

  it('shows which token was used', () => {
    expect(accessReason(t, 'token_access', 'api_token:sfn_ab12cd34')).toContain('sfn_ab12cd34')
  })

  it('shows an unknown reason as it came, and nothing when there is none', () => {
    expect(accessReason(t, 'session_revoked', 'something_new')).toBe('something_new')
    expect(accessReason(t, 'login', null)).toBeNull()
  })

  it('does not show the numbers of a lock as if they were a reason', () => {
    expect(accessReason(t, 'account_locked', '5 attempts, 15 min')).toBeNull()
  })
})
```

Run `npx vitest run src/lib/access-log.test.ts` (in `frontend/`). Expected: FAIL (module missing).

- [ ] **Step 4: Implement the helper**

`frontend/src/lib/access-log.ts`:

```ts
import type { TFunction } from 'i18next'

/** The audit actions that are accesses to the application (the same set the server reads). */
export const ACCESS_ACTIONS = [
  'login',
  'login_failed',
  'login_blocked',
  'account_locked',
  'account_unlocked',
  'session_revoked',
  'token_access',
] as const

/** What happened, in the person's language. An action this version does not know is shown as it came. */
export function accessAction(t: TFunction, action: string): string {
  return t(`accessLog.actions.${action}`, { defaultValue: action })
}

/**
 * Why, when the event says: "wrong password", "ended from another device", "token sfn_ab12cd34".
 * Null when there is nothing worth adding (a lock's detail is only numbers).
 */
export function accessReason(t: TFunction, action: string, detail: string | null): string | null {
  if (!detail) return null
  if (action === 'token_access') return t('accessLog.reasons.token', { prefix: detail.replace(/^api_token:/, '') })
  if (action === 'account_locked') return null
  return t(`accessLog.reasons.${detail}`, { defaultValue: detail })
}
```

Run `npx vitest run src/lib/access-log.test.ts`. Expected: 5 tests pass.

- [ ] **Step 5: Write the failing test for the page**

`frontend/src/pages/admin/access-log.test.tsx`:

```tsx
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'

import AccessLogPage from '@/pages/admin/access-log'
import { renderWithProviders, t } from '@/test/utils'

const api = vi.hoisted(() => ({
  accessLog: { list: vi.fn(), exportCsv: vi.fn(), retention: vi.fn() },
  admin: { listUsers: vi.fn() },
}))
vi.mock('@/lib/api', () => ({ accessLog: api.accessLog, admin: api.admin }))

const failed = {
  id: 'e1', seq: 7, occurred_at: '2026-03-01T12:00:00Z', actor_user_id: 'u1', actor_email: 'ana@example.com',
  actor_kind: 'user', workspace_id: null, action: 'login_failed', entity_type: 'user', entity_id: 'u1',
  changes: null, ip: '198.51.100.7', user_agent: 'Mozilla/5.0 Firefox', request_id: 'req-1', detail: 'bad_password',
  hash: 'a'.repeat(64),
}
const unknown = { ...failed, id: 'e2', actor_user_id: null, actor_email: null, detail: 'unknown_user', ip: '203.0.113.9' }

beforeEach(() => {
  vi.clearAllMocks()
  api.accessLog.retention.mockResolvedValue({ days: 183, minimum: 183, maximum: 3650 })
  api.accessLog.list.mockResolvedValue({ items: [failed, unknown], total: 2, page: 1, limit: 50 })
  api.admin.listUsers.mockResolvedValue({ items: [{ id: 'u2', email: 'bruno@example.com' }], total: 1 })
})

describe('access log page', () => {
  it('lists who tried what, from where, and why it failed', async () => {
    renderWithProviders(<AccessLogPage />)

    expect(await screen.findByText('ana@example.com')).toBeInTheDocument()
    expect(screen.getAllByText(new RegExp(t('accessLog.actions.login_failed')))).not.toHaveLength(0)
    expect(screen.getByText(/wrong password/)).toBeInTheDocument()
    expect(screen.getByText('203.0.113.9')).toBeInTheDocument()
  })

  it('tells how long the records are kept', async () => {
    renderWithProviders(<AccessLogPage />)
    expect(await screen.findByText(/Kept for 183 days/)).toBeInTheDocument()
  })

  it('asks the server for the filtered page', async () => {
    renderWithProviders(<AccessLogPage />)
    await screen.findByText('ana@example.com')

    fireEvent.change(screen.getByLabelText(t('accessLog.action')), { target: { value: 'login_failed' } })
    fireEvent.change(screen.getByLabelText(t('accessLog.ip')), { target: { value: '203.0.113.9' } })
    fireEvent.click(screen.getByRole('button', { name: t('accessLog.filter') }))

    await waitFor(() =>
      expect(api.accessLog.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ action: 'login_failed', ip: '203.0.113.9' }),
        1,
        50,
      ),
    )
  })

  it('exports what is filtered', async () => {
    api.accessLog.exportCsv.mockResolvedValue(undefined)
    renderWithProviders(<AccessLogPage />)
    await screen.findByText('ana@example.com')

    fireEvent.click(screen.getByRole('button', { name: t('accessLog.export') }))

    await waitFor(() => expect(api.accessLog.exportCsv).toHaveBeenCalledWith({}))
  })

  it('says so when there is nothing to show', async () => {
    api.accessLog.list.mockResolvedValue({ items: [], total: 0, page: 1, limit: 50 })
    renderWithProviders(<AccessLogPage />)
    expect(await screen.findByText(t('accessLog.empty'))).toBeInTheDocument()
  })
})
```

Run `npx vitest run src/pages/admin/access-log.test.tsx`. Expected: FAIL (page missing).

- [ ] **Step 6: Implement the page**

`frontend/src/pages/admin/access-log.tsx`:

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Download } from 'lucide-react'
import { accessLog as accessLogApi, admin as adminApi } from '@/lib/api'
import { ACCESS_ACTIONS, accessAction, accessReason } from '@/lib/access-log'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { AccessLogFilters, AuditEvent } from '@/types'

const PAGE_SIZE = 50

const SELECT_CLASS =
  'h-9 w-full rounded-lg border border-input bg-transparent px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring'

/** Who got into the instance, or tried to, and from where. Administrator only (the route enforces it). */
export default function AccessLogPage() {
  const { t, i18n } = useTranslation()
  const [draft, setDraft] = useState<AccessLogFilters>({})
  const [filters, setFilters] = useState<AccessLogFilters>({})
  const [page, setPage] = useState(1)

  const retention = useQuery({ queryKey: ['access-log-retention'], queryFn: accessLogApi.retention })
  const people = useQuery({ queryKey: ['access-log-people'], queryFn: () => adminApi.listUsers({ limit: 100 }) })
  const events = useQuery({
    queryKey: ['access-log', filters, page],
    queryFn: () => accessLogApi.list(filters, page, PAGE_SIZE),
  })
  const exporting = useMutation({
    mutationFn: () => accessLogApi.exportCsv(filters),
    onError: () => toast.error(t('accessLog.exportFailed')),
  })

  const total = events.data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const when = new Intl.DateTimeFormat(i18n.language, { dateStyle: 'short', timeStyle: 'medium' })

  function apply() {
    setPage(1)
    setFilters({ ...draft })
  }

  function personLabel(event: AuditEvent): string {
    if (event.actor_email) return event.actor_email
    if (event.actor_kind === 'api_token') return t('accessLog.apiToken')
    return event.actor_user_id ? t('accessLog.deletedUser') : '—'
  }

  return (
    <div className="container max-w-6xl py-8">
      <PageHeader
        section={t('accessLog.section')}
        title={t('accessLog.title')}
        action={
          <Button size="sm" onClick={() => exporting.mutate()} disabled={exporting.isPending}>
            <Download className="mr-2 h-4 w-4" />
            {t('accessLog.export')}
          </Button>
        }
      />
      <p className="mb-4 max-w-3xl text-sm text-muted-foreground">
        {t('accessLog.description', { days: retention.data?.days ?? 183 })}
      </p>

      <section className="mb-4 grid gap-3 rounded-xl border bg-card p-4 sm:grid-cols-2 lg:grid-cols-6">
        <div className="space-y-1.5">
          <Label htmlFor="access-from" className="text-[13px]">
            {t('accessLog.from')}
          </Label>
          <Input
            id="access-from"
            type="date"
            value={draft.from?.slice(0, 10) ?? ''}
            onChange={(e) => setDraft({ ...draft, from: e.target.value ? `${e.target.value}T00:00:00` : undefined })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="access-to" className="text-[13px]">
            {t('accessLog.to')}
          </Label>
          <Input
            id="access-to"
            type="date"
            value={draft.to?.slice(0, 10) ?? ''}
            onChange={(e) => setDraft({ ...draft, to: e.target.value ? `${e.target.value}T23:59:59` : undefined })}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="access-person" className="text-[13px]">
            {t('accessLog.person')}
          </Label>
          <select
            id="access-person"
            className={SELECT_CLASS}
            value={draft.actor_user_id ?? ''}
            onChange={(e) => setDraft({ ...draft, actor_user_id: e.target.value || undefined })}
          >
            <option value="">{t('accessLog.all')}</option>
            {(people.data?.items ?? []).map((person) => (
              <option key={person.id} value={person.id}>
                {person.email}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="access-action" className="text-[13px]">
            {t('accessLog.action')}
          </Label>
          <select
            id="access-action"
            className={SELECT_CLASS}
            value={draft.action ?? ''}
            onChange={(e) => setDraft({ ...draft, action: e.target.value || undefined })}
          >
            <option value="">{t('accessLog.all')}</option>
            {ACCESS_ACTIONS.map((name) => (
              <option key={name} value={name}>
                {accessAction(t, name)}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="access-ip" className="text-[13px]">
            {t('accessLog.ip')}
          </Label>
          <Input
            id="access-ip"
            value={draft.ip ?? ''}
            onChange={(e) => setDraft({ ...draft, ip: e.target.value.trim() || undefined })}
          />
        </div>
        <div className="flex items-end">
          <Button className="w-full" onClick={apply}>
            {t('accessLog.filter')}
          </Button>
        </div>
      </section>

      <section className="rounded-xl border bg-card">
        {events.isLoading ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        ) : events.isError ? (
          <p className="p-6 text-sm text-destructive">{t('accessLog.loadFailed')}</p>
        ) : events.data && events.data.items.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">{t('accessLog.empty')}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('accessLog.when')}</TableHead>
                <TableHead>{t('accessLog.who')}</TableHead>
                <TableHead>{t('accessLog.action')}</TableHead>
                <TableHead>{t('accessLog.ip')}</TableHead>
                <TableHead>{t('accessLog.device')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {events.data?.items.map((event) => {
                const reason = accessReason(t, event.action, event.detail)
                return (
                  <TableRow key={event.id}>
                    <TableCell className="whitespace-nowrap text-sm">{when.format(new Date(event.occurred_at))}</TableCell>
                    <TableCell className="text-sm">{personLabel(event)}</TableCell>
                    <TableCell className="text-sm">
                      {accessAction(t, event.action)}
                      {reason && <span className="text-muted-foreground"> · {reason}</span>}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-sm">{event.ip ?? '—'}</TableCell>
                    <TableCell className="max-w-[16rem] truncate text-sm text-muted-foreground" title={event.user_agent ?? undefined}>
                      {event.user_agent ?? '—'}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </section>

      {total > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-end gap-3 text-sm">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            {t('accessLog.previous')}
          </Button>
          <span className="text-muted-foreground">{t('accessLog.pageOf', { page, pages })}</span>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>
            {t('accessLog.next')}
          </Button>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 7: Add the route**

In `frontend/src/App.tsx`, replace the line `const AuditPage = lazy(() => import('@/pages/audit'))` with:

```tsx
const AuditPage = lazy(() => import('@/pages/audit'))
const AccessLogPage = lazy(() => import('@/pages/admin/access-log'))
```

and replace the line `<Route path="/admin" element={<AdminRoute><AdminSettingsPage /></AdminRoute>} />` (keep its leading whitespace on the first line of `new_string`) with itself plus, on the next line with the same indentation:

```tsx
<Route path="/admin/access-log" element={<AdminRoute><AccessLogPage /></AdminRoute>} />
```

- [ ] **Step 8: Run the checks**

Run in `frontend/`: `npx vitest run src/lib/access-log.test.ts src/pages/admin/access-log.test.tsx`, `npm run typecheck`, `npm run lint`, `npm run i18n:check -- --strict`.
Expected: 10 tests pass; typecheck, lint and i18n clean. If `getByLabelText(t('accessLog.action'))` finds two elements, the table header text is not a label and should not match; if it does, rename the test query to the select by id.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/locales frontend/src/types/index.ts frontend/src/lib/api.ts frontend/src/lib/access-log.ts frontend/src/lib/access-log.test.ts frontend/src/pages/admin frontend/src/App.tsx
git commit -m "feat: página Registros de acesso para o administrador (D3)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 6: Cartão "Prazo de guarda" em Administração

**Files:**
- Create: `frontend/src/components/admin/access-retention-card.tsx`
- Create: `frontend/src/components/admin/access-retention-card.test.tsx`
- Modify: `frontend/src/pages/admin/settings.tsx`

**Interfaces:**
- Consumes: `accessLog.retention()` e `accessLog.setRetention(days)` de `@/lib/api` (Task 5); chaves `admin.accessRetention.*` (Task 5); rota `/admin/access-log` (Task 5).
- Produces: `AccessRetentionCard` (sem props), exportado nomeado de `@/components/admin/access-retention-card`.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/admin/access-retention-card.test.tsx`:

```tsx
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { AccessRetentionCard } from '@/components/admin/access-retention-card'
import { renderWithProviders, t } from '@/test/utils'

const accessLog = vi.hoisted(() => ({ retention: vi.fn(), setRetention: vi.fn() }))
vi.mock('@/lib/api', () => ({ accessLog }))

const LIMITS = { minimum: 183, maximum: 3650 }

beforeEach(() => {
  vi.clearAllMocks()
  accessLog.retention.mockResolvedValue({ days: 183, ...LIMITS })
  accessLog.setRetention.mockImplementation(async (days: number) => ({ days, ...LIMITS }))
})

describe('AccessRetentionCard', () => {
  it('shows the period in force', async () => {
    renderWithProviders(<AccessRetentionCard />)
    expect(await screen.findByLabelText(t('admin.accessRetention.days'))).toHaveValue(183)
  })

  it('saves a longer period', async () => {
    const { user } = renderWithProviders(<AccessRetentionCard />)
    const field = await screen.findByLabelText(t('admin.accessRetention.days'))

    await user.clear(field)
    await user.type(field, '400')
    await user.click(screen.getByRole('button', { name: t('admin.accessRetention.save') }))

    await waitFor(() => expect(accessLog.setRetention).toHaveBeenCalledWith(400))
  })

  it('refuses a period outside the limits before asking the server', async () => {
    const { user } = renderWithProviders(<AccessRetentionCard />)
    const field = await screen.findByLabelText(t('admin.accessRetention.days'))

    await user.clear(field)
    await user.type(field, '100')

    expect(screen.getByText(t('admin.accessRetention.invalid', LIMITS))).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('admin.accessRetention.save') })).toBeDisabled()
  })

  it('warns that a shorter period anonymizes older records', async () => {
    accessLog.retention.mockResolvedValue({ days: 400, ...LIMITS })
    const { user } = renderWithProviders(<AccessRetentionCard />)
    const field = await screen.findByLabelText(t('admin.accessRetention.days'))

    await user.clear(field)
    await user.type(field, '200')

    expect(screen.getByText(t('admin.accessRetention.shorter'))).toBeInTheDocument()
    expect(screen.getByRole('button', { name: t('admin.accessRetention.save') })).toBeEnabled()
  })

  it('leads to the access log', async () => {
    renderWithProviders(<AccessRetentionCard />)
    const link = await screen.findByRole('link', { name: t('admin.accessRetention.viewLog') })
    expect(link).toHaveAttribute('href', '/admin/access-log')
  })
})
```

Run `npx vitest run src/components/admin/access-retention-card.test.tsx` (in `frontend/`). Expected: FAIL (component missing).

- [ ] **Step 2: Implement the card**

`frontend/src/components/admin/access-retention-card.tsx`:

```tsx
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { History } from 'lucide-react'
import { accessLog as accessLogApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'

const KEY = ['access-log-retention'] as const

/** How long sign-in and access records are kept before they are anonymized (a system parameter). */
export function AccessRetentionCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: KEY, queryFn: accessLogApi.retention })
  // What the person is typing; until they type, the saved value is shown.
  const [draft, setDraft] = useState<string | null>(null)
  const text = draft ?? String(data?.days ?? '')
  const days = Number(text)
  const limits = { min: data?.minimum ?? 183, max: data?.maximum ?? 3650 }
  const valid = !!data && text.trim() !== '' && Number.isInteger(days) && days >= limits.min && days <= limits.max
  const changed = !!data && days !== data.days
  const shorter = valid && !!data && days < data.days

  const save = useMutation({
    mutationFn: () => accessLogApi.setRetention(days),
    onSuccess: () => {
      setDraft(null)
      void queryClient.invalidateQueries({ queryKey: KEY })
      toast.success(t('admin.accessRetention.saved'))
    },
    onError: () => toast.error(t('common.error')),
  })

  return (
    <div className="mt-6 rounded-xl border border-border/60 bg-card overflow-hidden">
      <div className="px-5 py-4 border-b border-border/40">
        <div className="flex items-center gap-2 mb-0.5">
          <History size={15} className="text-muted-foreground" />
          <h3 className="text-sm font-semibold text-foreground">{t('admin.accessRetention.title')}</h3>
        </div>
        <p className="text-xs text-muted-foreground">{t('admin.accessRetention.description', limits)}</p>
      </div>

      {isLoading || !data ? (
        <div className="p-5">
          <Skeleton className="h-8 w-48" />
        </div>
      ) : (
        <div className="space-y-3 px-5 py-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="access-retention-days" className="text-[13px]">
                {t('admin.accessRetention.days')}
              </Label>
              <Input
                id="access-retention-days"
                type="number"
                min={limits.min}
                max={limits.max}
                value={text}
                disabled={save.isPending}
                onChange={(e) => setDraft(e.target.value)}
                className="h-10 w-32 rounded-lg"
              />
            </div>
            <Button disabled={!valid || !changed || save.isPending} onClick={() => save.mutate()}>
              {t('admin.accessRetention.save')}
            </Button>
          </div>
          <p className={`text-[11px] ${valid ? 'text-muted-foreground' : 'text-destructive'}`}>
            {valid ? t('admin.accessRetention.hint', limits) : t('admin.accessRetention.invalid', limits)}
          </p>
          {shorter && <p className="text-xs text-amber-600 dark:text-amber-500">{t('admin.accessRetention.shorter')}</p>}
          <Link to="/admin/access-log" className="inline-block text-xs font-medium text-primary hover:underline">
            {t('admin.accessRetention.viewLog')}
          </Link>
        </div>
      )}
    </div>
  )
}
```

Run `npx vitest run src/components/admin/access-retention-card.test.tsx`. Expected: 5 tests pass.

- [ ] **Step 3: Put the card on the administration page**

In `frontend/src/pages/admin/settings.tsx`, replace the line `import { MfaPolicyCard } from '@/components/admin/mfa-policy-card'` with:

```tsx
import { MfaPolicyCard } from '@/components/admin/mfa-policy-card'
import { AccessRetentionCard } from '@/components/admin/access-retention-card'
```

and replace the line `      <MfaPolicyCard />` with:

```tsx
      <MfaPolicyCard />
      <AccessRetentionCard />
```

- [ ] **Step 4: Run the checks**

Run in `frontend/`: `npx vitest run src/components/admin src/pages/admin`, `npm run typecheck`, `npm run lint`.
Expected: all pass. (If a test of `admin/settings.tsx` exists and mocks `@/lib/api` without `accessLog`, add `accessLog: { retention: vi.fn().mockResolvedValue({ days: 183, minimum: 183, maximum: 3650 }), setRetention: vi.fn() }` to its mock.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/admin frontend/src/pages/admin/settings.tsx
git commit -m "feat: cartão do prazo de guarda dos registros de acesso em Administração (D3)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: "Últimos acessos" no diálogo de sessões

**Files:**
- Modify: `frontend/src/components/sessions-dialog.tsx`
- Create: `frontend/src/components/sessions-dialog-access.test.tsx`

**Interfaces:**
- Consumes: `auth.accessHistory(limit)` de `@/lib/api`, `accessAction`/`accessReason` de `@/lib/access-log`, tipo `AccessHistoryItem`, chaves `auth.recentAccess.*` e `accessLog.*` (Task 5).
- Produces: seção "Últimos acessos" (20 mais recentes) no diálogo; nada mais.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/sessions-dialog-access.test.tsx`:

```tsx
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'

import { SessionsDialog } from '@/components/sessions-dialog'
import { renderWithProviders, t } from '@/test/utils'

const auth = vi.hoisted(() => ({
  listSessions: vi.fn(),
  revokeSession: vi.fn(),
  revokeOtherSessions: vi.fn(),
  accessHistory: vi.fn(),
}))
vi.mock('@/lib/api', () => ({ auth }))

const devices = [
  { id: 's1', device_label: 'Firefox em Windows', ip: '198.51.100.7', auth_method: 'password', created_at: '2026-03-01T10:00:00Z', last_seen_at: '2026-03-01T12:00:00Z', current: true },
]
const history = {
  items: [
    { id: 'a1', occurred_at: '2026-03-01T12:00:00Z', action: 'login_failed', actor_kind: 'user', detail: 'bad_password', ip: '203.0.113.9', user_agent: 'Firefox' },
    { id: 'a2', occurred_at: '2026-03-01T09:00:00Z', action: 'login', actor_kind: 'user', detail: 'password', ip: '198.51.100.7', user_agent: 'Firefox' },
  ],
  total: 2,
  page: 1,
  limit: 20,
}

beforeEach(() => {
  vi.clearAllMocks()
  auth.listSessions.mockResolvedValue(devices)
  auth.accessHistory.mockResolvedValue(history)
})

describe('SessionsDialog recent access', () => {
  it('lists the recent accesses with what happened, why and from where', async () => {
    renderWithProviders(<SessionsDialog open onClose={() => {}} />)

    expect(await screen.findByText(t('auth.recentAccess.title'))).toBeInTheDocument()
    expect(
      screen.getByText(`${t('accessLog.actions.login_failed')} · ${t('accessLog.reasons.bad_password')}`),
    ).toBeInTheDocument()
    expect(screen.getByText(/203\.0\.113\.9/)).toBeInTheDocument()
    expect(auth.accessHistory).toHaveBeenCalledWith(20)
  })

  it('says so when nothing has been recorded', async () => {
    auth.accessHistory.mockResolvedValue({ items: [], total: 0, page: 1, limit: 20 })
    renderWithProviders(<SessionsDialog open onClose={() => {}} />)

    expect(await screen.findByText(t('auth.recentAccess.empty'))).toBeInTheDocument()
  })

  it('keeps the devices when the history cannot be read, and hides the section', async () => {
    auth.accessHistory.mockRejectedValue(new Error('down'))
    renderWithProviders(<SessionsDialog open onClose={() => {}} />)

    expect(await screen.findByText('Firefox em Windows')).toBeInTheDocument()
    await waitFor(() => expect(auth.accessHistory).toHaveBeenCalled())
    expect(screen.queryByText(t('auth.recentAccess.title'))).not.toBeInTheDocument()
  })
})
```

Run `npx vitest run src/components/sessions-dialog-access.test.tsx` (in `frontend/`). Expected: FAIL (the section does not exist).

- [ ] **Step 2: Implement the section**

In `frontend/src/components/sessions-dialog.tsx` (each `old_string` is a single line):

1. Replace `import type { DeviceSession } from '@/types'` with:

```tsx
import { accessAction, accessReason } from '@/lib/access-log'
import type { AccessHistoryItem, DeviceSession } from '@/types'
```

2. Replace `  const [endingOthers, setEndingOthers] = useState(false)` with:

```tsx
  const [endingOthers, setEndingOthers] = useState(false)
  // null: not loaded, or it could not be read (then the section is simply not shown).
  const [recent, setRecent] = useState<AccessHistoryItem[] | null>(null)
```

3. Replace the line `  }, [])` (the end of the `load` callback; the only line with exactly that text) with:

```tsx
    // The recent accesses are a bonus: if they cannot be read, the devices above still work.
    try {
      setRecent((await auth.accessHistory(20)).items)
    } catch {
      setRecent(null)
    }
  }, [])
```

4. Replace `      <DialogContent className="sm:max-w-lg">` with:

```tsx
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
```

5. Replace the line `      </DialogContent>` with:

```tsx
        {recent && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold">{t('auth.recentAccess.title')}</h3>
            {recent.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t('auth.recentAccess.empty')}</p>
            ) : (
              <ul className="divide-y rounded-lg border">
                {recent.map((item) => {
                  const reason = accessReason(t, item.action, item.detail)
                  return (
                    <li key={item.id} className="px-3 py-2">
                      <p className="text-sm">{[accessAction(t, item.action), reason].filter(Boolean).join(' · ')}</p>
                      <p className="text-xs text-muted-foreground">
                        {when.format(new Date(item.occurred_at))}
                        {item.ip ? ` · ${item.ip}` : ''}
                      </p>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        )}
      </DialogContent>
```

- [ ] **Step 3: Run the checks**

Run in `frontend/`: `npx vitest run src/components/sessions-dialog-access.test.tsx src/components/sessions-dialog.test.tsx`, `npm run typecheck`, `npm run lint`.
Expected: the new 3 tests and the existing dialog tests pass (the existing mock has no `accessHistory`; the call throws inside the `try` and the section stays hidden, as intended).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/sessions-dialog.tsx frontend/src/components/sessions-dialog-access.test.tsx
git commit -m "feat: últimos acessos da própria pessoa no diálogo de sessões (D3)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

### Task 8: Documentação e manual

**Files:**
- Modify: `docs/FEATURES.md` (novo §15), `docs/CONFIGURATION.md`, `docs/ENTERPRISE.md`, `docs/FASE1.md`
- Modify: `frontend/src/help/content/pt-BR/administracao.md`, `frontend/src/help/content/pt-BR/seguranca-conta.md`
- Regenerate: `docs/MANUAL.md`

**Interfaces:**
- Consumes: tudo o que as tasks 1 a 7 entregaram (nomes de arquivos, rotas, parâmetro, tarefa).
- Produces: documentação; nenhum código.

- [ ] **Step 1: Write the FEATURES section**

Write to `C:\Users\gusta\AppData\Local\Temp\claude\d--Projeto-Finance\52652492-91ef-4104-96ad-0b5302c8eda6\scratchpad\features_15.md`:

```markdown


---

## 15. Registros de acesso

`core/access_log.py` · `services/access_log_service.py` · `api/access_log.py` · `tasks/audit_tasks.py` (`purge_access_log`) ·
`models/audit.py` · migração `099` · `pages/admin/access-log.tsx`, `components/admin/access-retention-card.tsx`,
`components/sessions-dialog.tsx` · desenho em [FASE1](FASE1.md) (item D3) e
[o spec](superpowers/specs/2026-09-21-registros-de-acesso-design.md)

Quem entrou, quem tentou e não conseguiu, de onde, e por quanto tempo isso fica guardado. Os registros são eventos da
[trilha de auditoria](#9-trilha-de-auditoria) (append-only, com cadeia de hashes); o D3 dá a eles consulta própria, um evento que
faltava e um prazo de guarda.

- **O que é um acesso:** `login`, `login_failed` (senha errada, código de 2FA errado, conta desativada, e-mail desconhecido),
  `login_blocked`, `account_locked`, `account_unlocked`, `session_revoked` (sair, encerrar em outro dispositivo, trocar a senha) e
  `token_access`. Cada um traz data e hora (do banco, em UTC), IP e navegador da requisição.
- **Uso de token de API (`token_access`):** um token não tem login, então o acesso é registrado quando ele autentica: **um evento por
  token e por IP a cada hora** (chave no Redis com validade de 1 h). O primeiro uso e um IP novo aparecem na hora. Token inválido,
  expirado ou revogado **não** gera evento, para a trilha não ser enchida por quem não tem credencial. Se o Redis falhar, o evento é
  gravado mesmo assim, e a requisição nunca falha por causa do registro.
- **Para o administrador:** *Administração → Registros de acesso* (`GET /api/admin/access-log`) lista com filtros (período, pessoa,
  IP, tipo de evento) e exporta CSV com os hashes (`/export`). Só o administrador da instância; token de API não acessa. Consultar não
  grava evento.
- **Para cada pessoa:** em *Sessões e dispositivos*, a seção **Últimos acessos** (`GET /api/auth/access-history`) mostra os 20 acessos
  mais recentes da própria conta, incluindo falhas de login: é como alguém percebe que tentaram entrar. A pessoa vem da sessão, nunca
  do pedido: não há como ver o acesso de outra.
- **Prazo de guarda:** o parâmetro `access_log_retention_days` (Administração, cartão *Prazo de guarda dos registros de acesso*;
  `GET|PUT /api/admin/access-log/retention`) vai de **183 a 3650 dias**, com padrão 183 (o mínimo do Marco Civil, art. 15, é de 6
  meses). Sem valor salvo, vale `ACCESS_LOG_RETENTION_DAYS`. Mudar o prazo entra na trilha como qualquer parâmetro.
- **Depois do prazo, anonimização:** uma tarefa diária (`purge_access_log`) zera pessoa, IP, navegador, identificador da requisição,
  detalhe e a entidade dos eventos de acesso vencidos e marca `purged_at`. A linha **fica**, com data, tipo de evento e hashes, para a
  cadeia continuar verificável. Cada execução grava `access_log_purged` (quantos, e com que prazo). Consulta e histórico não mostram
  linhas anonimizadas.
- **O piso vale no banco:** o trigger que proíbe alterar a trilha ganhou uma única exceção: anonimizar evento de acesso, já selado, com
  **mais de 183 dias**, mudando só essas colunas. Um erro no código, ou um prazo salvo fora da faixa, não anonimiza um evento recente.
  Nada mais na trilha mudou: `UPDATE` e `DELETE` comuns continuam recusados.
- **Integridade:** `GET /api/audit/verify` continua conferindo a sequência e o encadeamento de **todas** as linhas; nas anonimizadas
  não recalcula o conteúdo (ele deixou de existir), e nas demais confere tudo, como antes.
- **Numa instância que já existia:** eventos de acesso com mais de 183 dias são anonimizados na primeira execução da tarefa, salvo se o
  administrador aumentar o prazo antes.
- **Limites conhecidos:** anonimizar não apaga a linha (sobram data, tipo e hashes, sem pessoa nem IP); o descarte dos demais eventos da
  trilha (mudanças de dados) não existe ainda (D2). O registro cobre o lado técnico do Marco Civil; se a sua instância se enquadra no art.
  15 é uma decisão jurídica de quem a opera. Não há alerta de IP incomum nem geolocalização.
```

- [ ] **Step 2: Write the script that applies the doc edits**

Write to `C:\Users\gusta\AppData\Local\Temp\claude\d--Projeto-Finance\52652492-91ef-4104-96ad-0b5302c8eda6\scratchpad\apply_docs_d3.py`, then run it with `python <that path>`. The docs are CRLF: the script keeps that.

```python
import os

DOCS = r"D:\Projeto Finance\FinanceBR-Interprise\docs"
HELP = r"D:\Projeto Finance\FinanceBR-Interprise\frontend\src\help\content\pt-BR"
SCRATCH = os.path.dirname(os.path.abspath(__file__))


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return fh.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def crlf(text):
    return text.replace("\r\n", "\n").replace("\n", "\r\n")


def replace_once(text, old, new, label):
    old, new = crlf(old), crlf(new)
    assert text.count(old) == 1, f"{label}: expected exactly one match, found {text.count(old)}"
    return text.replace(old, new)


# FEATURES.md: new section at the end
p = os.path.join(DOCS, "FEATURES.md")
t = read(p)
if not t.endswith("\r\n"):
    t += "\r\n"
t += crlf(read(os.path.join(SCRATCH, "features_15.md")))
write(p, t)

# CONFIGURATION.md: the environment default, after the lock row
p = os.path.join(DOCS, "CONFIGURATION.md")
t = read(p)
anchor = "| `LOGIN_LOCK_MINUTES` | `15` |"
i = t.index(anchor)
j = t.index("\r\n", i) + 2
row = (
    "| `ACCESS_LOG_RETENTION_DAYS` | `183` | Por quantos dias os registros de acesso (logins, falhas, bloqueios, sessões encerradas, uso de token) são guardados antes de serem **anonimizados** (pessoa, IP e navegador são removidos; a linha e os hashes ficam). Vai de 183 (o mínimo legal de 6 meses) a 3650. O administrador muda o valor em Administração; este é o que vale até ele mudar. Em instância existente, o que passar de 183 dias é anonimizado na primeira execução da tarefa diária. |\n"
)
t = t[:j] + crlf(row) + t[j:]
write(p, t)

# ENTERPRISE.md: status table and backlog table
p = os.path.join(DOCS, "ENTERPRISE.md")
t = read(p)
t = replace_once(
    t,
    "Falta o registro de acessos (D3: logins e falhas) |",
    "Os registros de acesso (logins e falhas) vieram no D3: [FEATURES §15](FEATURES.md#15-registros-de-acesso) |",
    "enterprise:c1",
)
t = replace_once(t, "Falta o relatório de acessos (D3) |", "O relatório de acessos veio no D3 |", "enterprise:c10")
t = replace_once(
    t,
    "| **C4** sessões seguras |",
    "| **D3** registros de acesso | ✅ registro de logins, falhas, bloqueios, sessões encerradas e uso de token de API, com consulta e CSV para o administrador e histórico próprio para cada pessoa; guarda de no mínimo 6 meses com **prazo configurável** (183 a 3650 dias) e **anonimização automática** depois dele, com o piso imposto pelo banco; ver [FEATURES §15](FEATURES.md#15-registros-de-acesso) |\n"
    "| **C4** sessões seguras |",
    "enterprise:d3-row",
)
t = replace_once(
    t,
    "| Logs de aplicação básicos | P1 | S |",
    "| ✅ Feito ([FEATURES §15](FEATURES.md#15-registros-de-acesso)); antes, logs de aplicação básicos | P1 | S |",
    "enterprise:d3-table",
)
write(p, t)

# FASE1.md: mark D3 as delivered
p = os.path.join(DOCS, "FASE1.md")
t = read(p)
t = replace_once(
    t,
    "## D1 / D3 — LGPD e registros de acesso\n",
    "## D1 / D3 — LGPD e registros de acesso\n\n"
    "> ✅ **D3 entregue** ([FEATURES §15](FEATURES.md#15-registros-de-acesso)). Diferenças em relação ao desenho: em vez de só reter, o\n"
    "> prazo de guarda é um **parâmetro** (183 a 3650 dias) e, vencido, o evento é **anonimizado** (a linha e os hashes ficam, para a cadeia\n"
    "> do C1 continuar verificável), com o piso de 183 dias imposto pelo trigger do banco. Há consulta e CSV para o administrador e\n"
    "> histórico próprio para cada pessoa. **D1 (canal do titular) segue pendente.**\n",
    "fase1:d3",
)
write(p, t)

# Help pages (the in-app manual)
p = os.path.join(HELP, "administracao.md")
t = read(p)
t = replace_once(
    t,
    "## Contabilidade: caixa ou competência\n",
    "## Registros de acesso e prazo de guarda\n\n"
    "**Registros de acesso** (em *Administração*) mostra quem entrou na instalação, quem tentou e não conseguiu, e de onde: logins,\n"
    "falhas de senha ou de código de 2FA, contas bloqueadas e desbloqueadas, sessões encerradas e o uso de tokens de API. Dá para filtrar\n"
    "por período, pessoa, IP e tipo de evento, e **exportar em CSV**. Ninguém consegue editar ou apagar esses registros.\n\n"
    "O cartão **Prazo de guarda dos registros de acesso** define por quantos dias eles ficam guardados: de **183 dias** (o mínimo legal de\n"
    "6 meses) a 3650. Passado o prazo, o registro é **anonimizado**: somem a pessoa, o IP e o navegador, e só ficam a data e o tipo do\n"
    "evento. Reduzir o prazo anonimiza os registros mais antigos na próxima execução da tarefa diária, e isso não pode ser desfeito.\n\n"
    "## Contabilidade: caixa ou competência\n",
    "help:admin-access",
)
write(p, t)

p = os.path.join(HELP, "seguranca-conta.md")
t = read(p)
t = replace_once(
    t,
    "## Backup dos seus dados\n",
    "## Últimos acessos\n\n"
    "Na janela **Sessões e dispositivos**, abaixo da lista de dispositivos, a seção **Últimos acessos** mostra os 20 acessos mais recentes\n"
    "à sua conta: quando entrou, quando alguém errou a senha ou o código de 2FA, quando uma sessão foi encerrada, e de qual endereço IP.\n"
    "Se aparecer uma tentativa que você não reconhece, troque a senha e encerre as outras sessões. Você só vê os acessos da sua própria\n"
    "conta, e eles são guardados pelo prazo que o administrador definiu, depois anonimizados.\n\n"
    "## Backup dos seus dados\n",
    "help:conta-access",
)
write(p, t)
print("ok")
```

Run it. Expected: prints `ok`. If it stops with `expected exactly one match`, read the named file around that text, adjust the `old` string in the script to what is really there, and rerun (the script only writes at the end of each file, so rerunning after a failure in a later file would append the FEATURES section twice: if that happens, `git checkout -- docs/FEATURES.md docs/CONFIGURATION.md` first).

- [ ] **Step 3: Regenerate the manual and check everything**

Run in `frontend/`: `npm run manual:build` then `npm run manual:check`. Expected: `docs/MANUAL.md` changes; the check passes.

Then in the repo root:
```
git diff --stat -- docs frontend/src/help
python -c "
for f in ['FEATURES.md','FASE1.md','CONFIGURATION.md','ENTERPRISE.md']:
    b=open('docs/'+f,'rb').read(); b.decode('utf-8'); print(f,'CRLF',b.count(b'\r\n'),'LF',b.count(b'\n'))
"
```
Expected: each file's CRLF count equals its LF count (no mixed endings) and everything decodes as UTF-8.

- [ ] **Step 4: Commit**

```bash
git add docs frontend/src/help
git commit -m "docs: registros de acesso, prazo de guarda e anonimização (D3)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Verificação completa, e2e no stack real e PR

**Files:**
- Create (não commitar): `C:\Users\gusta\AppData\Local\Temp\claude\d--Projeto-Finance\52652492-91ef-4104-96ad-0b5302c8eda6\scratchpad\e2e_d3.py`

**Interfaces:**
- Consumes: tudo das tasks 1 a 8. Stack de desenvolvimento: front `:3100`, API `:8100`, containers `syncrofin-enterprise-*`.

- [ ] **Step 1: Full backend suite, in the background**

Make sure the test database is up: `docker compose -f docker-compose.test.yml up -d`. Then, in `backend/`, run in the background (about 15 minutes; do not edit backend files while it runs):

```
TZ=UTC0 .venv/Scripts/python.exe -m pytest tests -n 4 -q -p no:cacheprovider > <scratchpad>/suite_d3.log 2>&1
```
Expected at the end: `N passed` and no failures. Any failure is a real regression of this work: fix it, then rerun the **whole** suite after the last edit.

- [ ] **Step 2: Static checks (while the suite runs)**

In `backend/`: `.venv/Scripts/ruff.exe check .`, `.venv/Scripts/ty.exe check .`, `.venv/Scripts/python.exe scripts/check_migration_chain.py`.
In `frontend/`: `npm run typecheck`, `npm run lint`, `npm run i18n:check -- --strict`, `npx vitest run`.
Expected: all clean; the migration chain reports head `099`.

- [ ] **Step 3: Apply the migration to the dev database**

Run: `MSYS_NO_PATHCONV=1 docker exec syncrofin-enterprise-backend-1 alembic upgrade head` then `MSYS_NO_PATHCONV=1 docker exec syncrofin-enterprise-backend-1 alembic current`.
Expected: `099 (head)`.

- [ ] **Step 4: Write and run the end-to-end script**

`e2e_d3.py` (in the scratchpad). It makes a person, promotes them to administrator in the dev database, and checks the whole flow over HTTP; old events are inserted straight into the table (allowed: only updates and deletes are refused) so the anonymising can be seen working.

```python
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = "http://localhost:8100/api"
email = f"e2e-d3-{uuid.uuid4().hex[:8]}@example.com"
GOOD = "frase-longa-e-segura-42"
BACKEND = "syncrofin-enterprise-backend-1"
DB = "syncrofin-enterprise-db-1"


def sh(*args):
    return subprocess.run(list(args), capture_output=True, text=True)


def reset_limits():
    sh("docker", "exec", "syncrofin-enterprise-redis-1", "sh", "-c",
       "redis-cli --scan --pattern 'rate_limit:*' | xargs -r redis-cli del")


def sql(statement):
    r = sh("docker", "exec", DB, "sh", "-c", f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "{statement}"')
    return r.stdout.strip()


def call(method, path, body=None, form=None, headers=None, raw=False):
    if path in ("/auth/login", "/auth/register"):
        reset_limits()
    data, h = None, dict(headers or {})
    if body is not None:
        data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
    if form is not None:
        data, h["Content-Type"] = urllib.parse.urlencode(form).encode(), "application/x-www-form-urlencoded"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            content = r.read()
            return r.status, (content.decode() if raw else (json.loads(content) if content else None))
    except urllib.error.HTTPError as e:
        content = e.read()
        try:
            return e.code, json.loads(content)
        except Exception:
            return e.code, content.decode(errors="replace")


ok = True


def check(label, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("PASS " if cond else "FAIL ") + label, extra)


status, _ = call("POST", "/auth/register", body={"email": email, "password": GOOD})
check("person registered", status in (200, 201), status)
sql(f"UPDATE users SET is_superuser = true WHERE email = '{email}'")
status, token = call("POST", "/auth/login", form={"username": email, "password": GOOD})
check("signed in as administrator", status == 200, status)
admin = {"Authorization": f"Bearer {token['access_token']}"}

# A wrong password leaves a mark.
call("POST", "/auth/login", form={"username": email, "password": "errada-1"})
status, page = call("GET", "/admin/access-log?limit=200", headers=admin)
actions = {item["action"] for item in page["items"]}
check("access log lists login and login_failed", {"login", "login_failed"} <= actions, sorted(actions))
status, page = call("GET", "/admin/access-log?action=login_failed", headers=admin)
check("filter by action", status == 200 and page["total"] >= 1 and all(i["action"] == "login_failed" for i in page["items"]))
check("unknown action refused", call("GET", "/admin/access-log?action=update", headers=admin)[0] == 422)

# The person's own history.
status, mine = call("GET", "/auth/access-history", headers=admin)
check("own history has the failure and the login", status == 200 and {"login", "login_failed"} <= {i["action"] for i in mine["items"]})
check("own history has no hash", "hash" not in mine["items"][0])

# An API token's use is recorded once per hour.
status, made = call("POST", "/api-tokens", body={"name": "e2e", "scopes": ["export.read"], "days": 7}, headers=admin)
check("token made", status == 201, status)
bearer = {"Authorization": f"Bearer {made['token']}"}
for _ in range(3):
    call("GET", "/accounts", headers=bearer)
status, page = call("GET", "/admin/access-log?action=token_access", headers=admin)
check("token use recorded exactly once", status == 200 and page["total"] == 1, page["total"])
check("a token cannot read the access log", call("GET", "/admin/access-log", headers=bearer)[0] == 403)

# CSV.
status, csv_text = call("GET", "/admin/access-log/export", headers=admin, raw=True)
check("csv export", status == 200 and csv_text.startswith("\ufeff") and "login_failed" in csv_text)

# Retention setting.
check("retention default", call("GET", "/admin/access-log/retention", headers=admin)[1]["days"] == 183)
check("retention refuses 100", call("PUT", "/admin/access-log/retention", body={"days": 100}, headers=admin)[0] == 422)
check("retention accepts 400", call("PUT", "/admin/access-log/retention", body={"days": 400}, headers=admin)[1]["days"] == 400)

# Anonymising: an old event, a middle-aged one and the recent ones.
sql("INSERT INTO audit_events (id, occurred_at, actor_kind, action, entity_type, ip, detail) VALUES "
    "(gen_random_uuid(), now() - interval '500 days', 'user', 'login', 'user_session', '192.0.2.10', 'password'), "
    "(gen_random_uuid(), now() - interval '300 days', 'user', 'login', 'user_session', '192.0.2.20', 'password')")
call("GET", "/admin/access-log/export", headers=admin, raw=True)  # seals what is pending
check("old events are visible before the purge", call("GET", "/admin/access-log?ip=192.0.2.10", headers=admin)[1]["total"] == 1)

run = sh("docker", "exec", BACKEND, "python", "-c",
         "import asyncio; from app.tasks.audit_tasks import _purge; print('PURGED', asyncio.run(_purge()))")
purged = [line for line in run.stdout.splitlines() if line.startswith("PURGED")]
check("purge with 400 days anonymises only the 500-day event", purged == ["PURGED 1"], purged or run.stderr[-300:])
check("the anonymised event is gone from the log", call("GET", "/admin/access-log?ip=192.0.2.10", headers=admin)[1]["total"] == 0)
check("the 300-day event is still there", call("GET", "/admin/access-log?ip=192.0.2.20", headers=admin)[1]["total"] == 1)
check("the row stayed, emptied", sql("SELECT count(*) FROM audit_events WHERE purged_at IS NOT NULL AND ip IS NULL AND detail IS NULL") != "0")
check("the trail still verifies", call("GET", "/audit/verify", headers=admin)[1]["ok"] is True, call("GET", "/audit/verify", headers=admin)[1])
check("the purge left a note", "access_log_purged" in json.dumps(call("GET", "/audit/instance?action=access_log_purged", headers=admin)[1]))

# The database keeps the floor, whatever the application says.
r = sh("docker", "exec", DB, "sh", "-c",
       'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT set_config(\'audit.purging\',\'on\',false); UPDATE audit_events SET ip = NULL, actor_user_id = NULL, entity_id = NULL, changes = NULL, user_agent = NULL, request_id = NULL, detail = NULL, purged_at = now() WHERE action = \'login\' AND occurred_at > now() - interval \'5 days\'"')
check("the database refuses to anonymise a recent event", "append-only" in (r.stdout + r.stderr), (r.stdout + r.stderr)[-200:])

# Put the retention back.
call("PUT", "/admin/access-log/retention", body={"days": 183}, headers=admin)

print("\nALL PASS" if ok else "\nSOME FAILED")
print("email:", email)
```

Run: `MSYS_NO_PATHCONV=1 python <scratchpad>/e2e_d3.py`. Expected: every line `PASS`, ending in `ALL PASS`. The script leaves an `e2e-d3-*@example.com` administrator and two anonymised/old test events in the **dev** database; tell the user.

Then look at the two screens in the browser (`http://localhost:3100`, sign in as that administrator): *Administração* shows the retention card, the link opens *Registros de acesso* with rows, and *Sessões e dispositivos* shows *Últimos acessos*. Report what was seen; if a screen was not opened, say so.

- [ ] **Step 5: Confirm the full suite ran after the last edit**

Read `<scratchpad>/suite_d3.log`: expected `N passed` and no `failed`. If any backend file changed after the suite started, rerun the suite before going on.

- [ ] **Step 6: Push and open the pull request**

```bash
git push -u origin feat/registros-de-acesso
gh pr create --base main --title "feat: registros de acesso, prazo de guarda e anonimização (D3)" --body-file <scratchpad>/pr_d3.md
```

Write `pr_d3.md` first, in Portuguese, with: **O que muda** (registro de acessos para o administrador, histórico próprio, `token_access`, prazo de guarda configurável, anonimização diária com piso no banco, migração 099), **Verificação** (números reais da suíte, ruff, ty, cadeia de migrações, vitest/tsc/eslint/i18n, e2e no stack real, e o que foi ou não visto no navegador), **Atenção ao revisar** (a exceção nova no trigger de `audit_events`, a primeira execução da tarefa em instância existente anonimiza o que passar de 183 dias, o CI não foi conferido) e a linha `🤖 Generated with [Claude Code](https://claude.com/claude-code)` no fim.

Expected: `gh` prints the PR URL. Do not merge; the user does. Tell the user the CI is not confirmed until they see it run.

