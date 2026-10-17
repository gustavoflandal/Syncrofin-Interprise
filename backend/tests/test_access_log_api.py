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


async def _wipe_trail(session: AsyncSession) -> None:
    """Drop what the sign-in fixtures already wrote (a `login` per signed-in person), so a test counts only its own events."""
    await session.execute(text("ALTER TABLE audit_events DISABLE TRIGGER USER"))
    await session.execute(text("DELETE FROM audit_events"))
    await session.execute(text("ALTER TABLE audit_events ENABLE TRIGGER USER"))
    await session.commit()


class TestTheAdministratorsView:
    async def test_it_lists_access_events_newest_first_and_only_those(
        self, client: AsyncClient, session: AsyncSession, test_user: User, admin_auth_headers: dict
    ):
        await _wipe_trail(session)
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
        await _wipe_trail(session)
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
        await _wipe_trail(session)
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
        await _wipe_trail(session)
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
        await _wipe_trail(session)
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
