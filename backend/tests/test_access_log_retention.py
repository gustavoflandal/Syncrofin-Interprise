"""How long access records are kept, and the daily anonymising once that is over."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_settings import AppSetting
from app.models.audit import AuditEvent
from app.services import access_log_service
from tests.access_log_helpers import add_event


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
        with patch("app.services.access_log_service.get_settings", return_value=SimpleNamespace(access_log_retention_days=183)):
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

    async def test_a_failing_later_batch_still_leaves_the_note_for_the_earlier_ones(self, session: AsyncSession):
        for _ in range(5):
            await add_event(session, age_days=400)
        real_text = access_log_service.text
        calls = 0

        def _text(sql):
            # The 2nd batch fails the way the database fails: the statement is rejected and the transaction is aborted.
            nonlocal calls
            if "audit_events_purge_access" in str(sql):
                calls += 1
                if calls == 2:
                    return real_text("SELECT audit_events_purge_access('not-a-number'::int, 1)")
            return real_text(sql)

        with patch.object(access_log_service, "text", _text):
            with pytest.raises(DBAPIError):
                await access_log_service.purge_expired(session, batch=2)

        assert len(await _purged_ids(session)) == 2
        notes = (await session.execute(select(AuditEvent).where(AuditEvent.action == "access_log_purged"))).scalars().all()
        assert [note.detail for note in notes] == ["2 events, 183 days"]

    async def test_a_batch_of_zero_still_ends_and_does_everything_due(self, session: AsyncSession):
        for _ in range(3):
            await add_event(session, age_days=400)

        assert await access_log_service.purge_expired(session, batch=0) == 3
        assert len(await _purged_ids(session)) == 3


def test_the_daily_job_is_scheduled():
    from celery.schedules import crontab

    from app.tasks import audit_tasks
    from app.worker import celery_app

    entry = celery_app.conf.beat_schedule["purge-access-log-daily"]
    assert entry["task"] == audit_tasks.purge_access_log.name == "app.tasks.audit_tasks.purge_access_log"
    schedule = entry["schedule"]
    assert isinstance(schedule, crontab)
    assert schedule.hour == {3} and schedule.minute == {30}
