"""Using an API token leaves a mark in the access log: once per token and address per hour."""
import sys
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
from unittest.mock import AsyncMock, patch

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

    async def delete(self, key):
        self.keys.discard(key)


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

    context = AuditContext()
    marker = audit_context.set(context)
    try:
        for ip in ("203.0.113.1", "203.0.113.1", "203.0.113.2"):
            context.ip = ip
            context.user_agent = "curl/8"
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


async def test_a_failure_writing_the_event_does_not_fail_the_request(
    client: AsyncClient, session: AsyncSession, auth_headers: dict, fake_redis: FakeRedis
):
    created = await _make_token(client, auth_headers)

    with patch("app.services.access_log_service.record_event", AsyncMock(side_effect=RuntimeError("db is down"))):
        response = await client.get("/api/accounts", headers=_bearer(created["token"]))

    assert response.status_code == 200
    assert await _events(session) == []


async def test_a_failed_write_is_tried_again_on_the_next_request(
    client: AsyncClient, session: AsyncSession, auth_headers: dict, fake_redis: FakeRedis
):
    created = await _make_token(client, auth_headers)

    with patch("app.services.access_log_service.record_event", AsyncMock(side_effect=RuntimeError("db is down"))):
        assert (await client.get("/api/accounts", headers=_bearer(created["token"]))).status_code == 200
    assert (await client.get("/api/accounts", headers=_bearer(created["token"]))).status_code == 200

    assert len(await _events(session)) == 1


async def test_a_failure_committing_the_event_does_not_fail_the_request(
    client: AsyncClient, session: AsyncSession, auth_headers: dict, fake_redis: FakeRedis
):
    """The commit is the last step of the log's write. It fails only for the caller inside `access_log_service`
    (any other commit in the request, such as the token's `last_used_at`, goes through untouched)."""
    created = await _make_token(client, auth_headers)
    real_commit = AsyncSession.commit

    async def _commit(self):
        if sys._getframe(1).f_globals.get("__name__") == access_log_service.__name__:
            raise RuntimeError("db is down")
        await real_commit(self)

    with patch.object(AsyncSession, "commit", _commit):
        response = await client.get("/api/accounts", headers=_bearer(created["token"]))

    assert response.status_code == 200
    assert await _events(session) == []
    assert fake_redis.keys == set()
    # The window was forgotten, so the next use records the access.
    assert (await client.get("/api/accounts", headers=_bearer(created["token"]))).status_code == 200
    assert len(await _events(session)) == 1


def _expire(row: ApiToken) -> None:
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)


def _revoke(row: ApiToken) -> None:
    row.revoked_at = datetime.now(timezone.utc)


@pytest.mark.parametrize("how", ["expired", "revoked", "user_deactivated"])
async def test_a_token_that_is_no_longer_good_gets_401_and_leaves_no_mark(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_headers: dict, fake_redis: FakeRedis, how: str
):
    created = await _make_token(client, auth_headers)
    row = (await session.execute(select(ApiToken))).scalar_one()
    if how == "expired":
        _expire(row)
    elif how == "revoked":
        _revoke(row)
    else:
        await session.execute(update(User).where(User.id == test_user.id).values(is_active=False))
    await session.commit()

    assert (await client.get("/api/accounts", headers=_bearer(created["token"]))).status_code == 401
    assert await _events(session) == []
