"""The Alembic migrations, run for real against PostgreSQL.

Every other test builds its schema from the models with `create_all`, which
proves the models work and says nothing about the migrations production
actually runs. A migration can be wrong in ways `create_all` never sees: a
column the model has and no migration adds, a downgrade that cannot undo its
own upgrade, a `server_default` that fails on existing rows.

So this builds a **fresh database with nothing but the migrations**, then
checks it agrees with the models. It runs Alembic as a subprocess: the app
caches its settings on import, and a migration run should see exactly the
environment a deploy gives it.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from app.core.database import Base
from tests.conftest import _ADMIN_URL

BACKEND = Path(__file__).resolve().parent.parent


async def _admin() -> asyncpg.Connection:
    u = make_url(_ADMIN_URL)
    return await asyncpg.connect(
        user=u.username, password=u.password, host=u.host, port=u.port or 5432,
        database=u.database or "postgres",
    )


def _alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": db_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=600,
    )


@pytest.fixture
async def fresh_db():
    """A brand-new database, dropped afterwards. Never shares state with the suite."""
    name = f"syncrofin_migr_{uuid.uuid4().hex[:10]}"
    admin = await _admin()
    await admin.execute(f'CREATE DATABASE "{name}"')
    await admin.close()
    url = make_url(_ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    try:
        yield name, url
    finally:
        admin = await _admin()
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.close()


async def _tables(name: str) -> set[str]:
    u = make_url(_ADMIN_URL)
    conn = await asyncpg.connect(
        user=u.username, password=u.password, host=u.host, port=u.port or 5432, database=name
    )
    try:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )
        return {r["table_name"] for r in rows}
    finally:
        await conn.close()


async def _columns(name: str, table: str) -> set[str]:
    u = make_url(_ADMIN_URL)
    conn = await asyncpg.connect(
        user=u.username, password=u.password, host=u.host, port=u.port or 5432, database=name
    )
    try:
        rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = $1",
            table,
        )
        return {r["column_name"] for r in rows}
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_migrations_build_the_schema_the_models_describe(fresh_db):
    name, url = fresh_db

    result = _alembic(url, "upgrade", "head")
    assert result.returncode == 0, result.stderr[-3000:]

    migrated = await _tables(name)
    expected = {table.name for table in Base.metadata.sorted_tables}
    assert expected - migrated == set(), "tables the models define but no migration creates"
    assert migrated - expected - {"alembic_version"} == set(), "tables a migration creates that no model knows"

    # Column-level agreement, table by table. This is what catches a model
    # field that was added without a migration (or the reverse).
    drift = {}
    for table in Base.metadata.sorted_tables:
        model_cols = {c.name for c in table.columns}
        db_cols = await _columns(name, table.name)
        if model_cols != db_cols:
            drift[table.name] = {"only_model": sorted(model_cols - db_cols), "only_db": sorted(db_cols - model_cols)}
    assert drift == {}


@pytest.mark.asyncio
async def test_the_latest_migrations_can_be_undone_and_redone(fresh_db):
    """Roll back the two most recent migrations and forward again.

    Full downgrade to base is not asserted: some historical migrations are
    data migrations that cannot honestly be reversed. What must always hold is
    that the migrations written *now* are reversible, since those are the ones
    a failed deploy will need to undo.
    """
    name, url = fresh_db
    assert _alembic(url, "upgrade", "head").returncode == 0

    heads = _alembic(url, "heads")
    assert heads.returncode == 0
    head = heads.stdout.split()[0]

    down = _alembic(url, "downgrade", "-2")
    assert down.returncode == 0, down.stderr[-3000:]
    assert _alembic(url, "current").stdout.strip() != head

    up = _alembic(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr[-3000:]
    assert head in _alembic(url, "current").stdout


@pytest.mark.asyncio
async def test_migration_091_and_092_add_what_the_models_expect(fresh_db):
    name, url = fresh_db
    assert _alembic(url, "upgrade", "head").returncode == 0

    assert "notifications" in await _tables(name)
    assert "reconciliation_auto_apply_score" in await _columns(name, "workspaces")


@pytest.mark.asyncio
async def test_the_migrated_audit_trail_is_append_only_and_seals(fresh_db):
    """The guards come from migration 093 in production, not from the models the suite uses."""
    name, url = fresh_db
    assert _alembic(url, "upgrade", "head").returncode == 0

    u = make_url(_ADMIN_URL)
    conn = await asyncpg.connect(
        user=u.username, password=u.password, host=u.host, port=u.port or 5432, database=name
    )
    try:
        await conn.execute(
            "INSERT INTO audit_events (id, actor_kind, action, entity_type) "
            "VALUES (gen_random_uuid(), 'system', 'create', 'accounts')"
        )
        for statement in ("UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events", "TRUNCATE audit_events"):
            with pytest.raises(asyncpg.PostgresError, match="append-only"):
                await conn.execute(statement)

        assert await conn.fetchval("SELECT audit_events_seal()") == 1
        row = await conn.fetchrow("SELECT seq, prev_hash, hash FROM audit_events")
        assert row["seq"] == 1 and row["prev_hash"] == "0" * 64 and len(row["hash"]) == 64
        assert await conn.fetchval("SELECT audit_events_seal()") == 0
    finally:
        await conn.close()
