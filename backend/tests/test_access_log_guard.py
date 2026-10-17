"""Anonymising an access event: what the database allows, what it refuses, and that the chain still verifies."""
import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access_log import ACCESS_ACTIONS, REDACTED_COLUMNS, sql_list
from app.models import audit as audit_module
from app.models.audit import VERIFY_QUERY
from tests.access_log_helpers import add_event

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
        await _refused(session, await add_event(session, age_days=400), set_clause=REDACT + ", action = 'login_failed'")

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

    async def test_calling_it_twice_over_the_same_rows_does_nothing_the_second_time(self, session: AsyncSession):
        for _ in range(3):
            await add_event(session, age_days=400)
        assert await _purge(session, 183) == 3
        assert await _purge(session, 183) == 0

    async def test_it_does_not_leave_the_purge_flag_on(self, session: AsyncSession):
        await add_event(session, age_days=400)
        await session.execute(text("SELECT audit_events_purge_access(183, 1000)"))
        flag = (await session.execute(text("SELECT current_setting('audit.purging', true)"))).scalar_one()
        assert flag in ("off", "", None)
        await session.rollback()

    async def test_it_leaves_other_events_alone(self, session: AsyncSession):
        other = await add_event(session, action="update", entity_type="accounts", age_days=400)
        assert await _purge(session, 183) == 0
        purged = (await session.execute(text("SELECT purged_at FROM audit_events WHERE id = :id"), {"id": other})).scalar_one()
        assert purged is None


    async def test_a_concurrent_run_skips_the_rows_another_one_holds(self, session: AsyncSession):
        from tests.conftest import TestSessionLocal

        for _ in range(3):
            await add_event(session, age_days=400)

        # Session A anonymises the three rows and keeps its locks (no commit yet).
        first = (await session.execute(text("SELECT audit_events_purge_access(183, 1000)"))).scalar_one()
        assert first == 3

        # Session B meets the locked rows: FOR UPDATE SKIP LOCKED makes it skip them at once (no wait, no error).
        async with TestSessionLocal() as other:
            try:
                second = await asyncio.wait_for(
                    other.execute(text("SELECT audit_events_purge_access(183, 1000)")), timeout=10
                )
                assert second.scalar_one() == 0
            finally:
                await other.rollback()

        await session.commit()
        purged = (await session.execute(text("SELECT count(*) FROM audit_events WHERE purged_at IS NOT NULL"))).scalar_one()
        assert purged == 3


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

    async def test_rewriting_an_anonymised_row_is_caught(self, session: AsyncSession):
        old = await add_event(session, age_days=400)
        await add_event(session, age_days=1)
        await _purge(session, 183)

        await session.execute(text("ALTER TABLE audit_events DISABLE TRIGGER USER"))
        await session.execute(text("UPDATE audit_events SET ip = '203.0.113.99' WHERE id = :id"), {"id": old})
        await session.execute(text("ALTER TABLE audit_events ENABLE TRIGGER USER"))
        await session.commit()

        found = (await session.execute(text(VERIFY_QUERY))).first()
        assert found is not None and found.reason == "purged row altered"

    async def test_a_recent_row_relabelled_as_anonymised_is_caught(self, session: AsyncSession):
        # Nothing younger than the floor is ever anonymised: a recent row that claims to be is a forgery,
        # whatever it used to be (here a full `update` row is passed off as an anonymised login).
        recent = await add_event(session, action="update", entity_type="accounts", age_days=1)

        await session.execute(text("ALTER TABLE audit_events DISABLE TRIGGER USER"))
        await session.execute(
            text(f"UPDATE audit_events SET {REDACT}, action = 'login' WHERE id = :id"), {"id": recent}
        )
        await session.execute(text("ALTER TABLE audit_events ENABLE TRIGGER USER"))
        await session.commit()

        found = (await session.execute(text(VERIFY_QUERY))).first()
        assert found is not None and found.reason == "purged row altered"

    async def test_turning_an_anonymised_row_into_another_action_is_caught(self, session: AsyncSession):
        old = await add_event(session, age_days=400)
        await _purge(session, 183)

        await session.execute(text("ALTER TABLE audit_events DISABLE TRIGGER USER"))
        await session.execute(text("UPDATE audit_events SET action = 'update' WHERE id = :id"), {"id": old})
        await session.execute(text("ALTER TABLE audit_events ENABLE TRIGGER USER"))
        await session.commit()

        found = (await session.execute(text(VERIFY_QUERY))).first()
        assert found is not None and found.reason == "purged row altered"

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
        path = BACKEND / "alembic" / "versions" / "101_erasure_password_failed_access_action.py"
        spec = importlib.util.spec_from_file_location("migration_101", path)
        assert spec is not None and spec.loader is not None
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)

        def flat(sql: str) -> str:
            return " ".join(sql.split())

        assert flat(migration.IMMUTABLE_FUNCTION) == flat(audit_module.IMMUTABLE_FUNCTION)
        assert flat(migration.PURGE_FUNCTION) == flat(audit_module.PURGE_FUNCTION)
        assert flat(f"WHERE action IN ({sql_list()}) AND purged_at IS NULL") in flat(migration.ACCESS_INDEX)

    def test_no_code_removes_rows_from_the_trail(self):
        source = "\n".join(path.read_text(encoding="utf-8") for path in (BACKEND / "app").rglob("*.py"))
        assert "DELETE FROM audit_events" not in source
        assert "delete(AuditEvent" not in source

    def test_every_access_action_is_recorded_somewhere_in_the_code(self):
        sources = [
            path.read_text(encoding="utf-8")
            for path in (BACKEND / "app").rglob("*.py")
            if path.name != "access_log.py"
        ]
        source = "\n".join(sources)
        for action in ACCESS_ACTIONS:
            assert f'"{action}"' in source, f"{action} is in ACCESS_ACTIONS but nothing records it"
