"""Sessions: a login that can be ended, listed and rotated."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi_users.jwt import generate_jwt
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit import AuditEvent
from app.models.user import User
from app.models.user_session import UserSession
from app.services import session_service

FORM = {"username": "test@example.com", "password": "testpass123"}


async def _login(client: AsyncClient, **headers) -> dict:
    response = await client.post("/api/auth/login", data=FORM, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _sid(token: str) -> str:
    claims = session_service.read_access_claims(token)
    assert claims is not None
    return claims["sid"]


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _rows(session: AsyncSession) -> list[UserSession]:
    result = await session.execute(
        select(UserSession).execution_options(populate_existing=True).order_by(UserSession.created_at)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
class TestSignIn:
    async def test_login_gives_a_short_access_token_and_an_httponly_refresh_cookie(
        self, client: AsyncClient, test_user: User
    ):
        response = await client.post("/api/auth/login", data=FORM)
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == get_settings().access_token_expire_minutes * 60
        assert "refresh_token" not in body, "the browser must never be able to read the refresh token"

        cookie = response.headers["set-cookie"].lower()
        assert "refresh_token=" in cookie
        assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api/auth" in cookie

    async def test_the_access_token_names_its_session_and_works(
        self, client: AsyncClient, session: AsyncSession, test_user: User
    ):
        body = await _login(client)
        me = await client.get("/api/users/me", headers=_bearer(body["access_token"]))
        assert me.status_code == 200 and me.json()["email"] == test_user.email

        claims = session_service.read_access_claims(body["access_token"])
        assert claims is not None
        [row] = await _rows(session)
        assert claims["sid"] == str(row.id)
        assert row.auth_method == "password" and row.revoked_at is None

    async def test_a_client_without_cookies_can_ask_for_the_refresh_token_in_the_body(
        self, client: AsyncClient, test_user: User
    ):
        response = await client.post("/api/auth/login", data=FORM, headers={"X-Refresh-Mode": "body"})
        assert response.json()["refresh_token"]
        assert "set-cookie" not in response.headers

    async def test_the_refresh_token_is_stored_only_as_a_hash(
        self, client: AsyncClient, session: AsyncSession, test_user: User
    ):
        body = await client.post("/api/auth/login", data=FORM, headers={"X-Refresh-Mode": "body"})
        token = body.json()["refresh_token"]
        [row] = await _rows(session)
        assert row.refresh_hash == session_service.hash_refresh_token(token)
        assert token not in (row.refresh_hash, row.previous_refresh_hash)

    async def test_the_device_is_described_for_a_person(
        self, client: AsyncClient, session: AsyncSession, test_user: User
    ):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0"
        await _login(client, **{"User-Agent": ua})
        [row] = await _rows(session)
        assert row.device_label == "Firefox em Windows"

    async def test_sign_in_is_in_the_audit_trail(
        self, client: AsyncClient, session: AsyncSession, test_user: User
    ):
        await _login(client)
        events = (await session.execute(select(AuditEvent).where(AuditEvent.action == "login"))).scalars().all()
        assert [e.entity_type for e in events] == ["user_session"]
        assert events[0].actor_user_id == test_user.id

    async def test_a_token_from_before_sessions_existed_is_refused(
        self, client: AsyncClient, test_user: User
    ):
        settings = get_settings()
        legacy = generate_jwt(
            {"sub": str(test_user.id), "aud": ["fastapi-users:auth"]},
            settings.secret_key.get_secret_value(),
            3600,
        )
        assert (await client.get("/api/users/me", headers=_bearer(legacy))).status_code == 401


@pytest.mark.asyncio
class TestRefresh:
    async def test_refresh_gives_a_new_access_token_and_rotates_the_cookie(
        self, client: AsyncClient, test_user: User
    ):
        first = await client.post("/api/auth/login", data=FORM)
        old_cookie = client.cookies.get("refresh_token")

        response = await client.post("/api/auth/refresh")
        assert response.status_code == 200, response.text
        assert client.cookies.get("refresh_token") != old_cookie
        me = await client.get("/api/users/me", headers=_bearer(response.json()["access_token"]))
        assert me.status_code == 200
        # The session is the same one: the new token names it too.
        assert _sid(response.json()["access_token"]) == _sid(first.json()["access_token"])

    async def test_without_a_cookie_there_is_no_session(self, client: AsyncClient, test_user: User):
        assert (await client.post("/api/auth/refresh")).status_code == 401

    async def test_a_garbage_refresh_token_is_refused(self, client: AsyncClient, test_user: User):
        client.cookies.set("refresh_token", "not-a-real-token", path="/api/auth")
        assert (await client.post("/api/auth/refresh")).status_code == 401

    async def test_body_mode_rotates_the_token_in_the_body(self, client: AsyncClient, test_user: User):
        login = await client.post("/api/auth/login", data=FORM, headers={"X-Refresh-Mode": "body"})
        first = login.json()["refresh_token"]
        refreshed = await client.post(
            "/api/auth/refresh", json={"refresh_token": first}, headers={"X-Refresh-Mode": "body"}
        )
        assert refreshed.status_code == 200
        second = refreshed.json()["refresh_token"]
        assert second and second != first
        assert "set-cookie" not in refreshed.headers

    async def test_a_second_tab_presenting_the_old_token_at_once_is_not_treated_as_theft(
        self, client: AsyncClient, test_user: User
    ):
        login = await client.post("/api/auth/login", data=FORM, headers={"X-Refresh-Mode": "body"})
        first = login.json()["refresh_token"]
        headers = {"X-Refresh-Mode": "body"}
        one = await client.post("/api/auth/refresh", json={"refresh_token": first}, headers=headers)
        two = await client.post("/api/auth/refresh", json={"refresh_token": first}, headers=headers)
        assert one.status_code == 200 and two.status_code == 200
        assert "refresh_token" not in two.json(), "the tab that lost the race keeps the token it already has"
        # ... and the token the first tab got still works.
        third = await client.post(
            "/api/auth/refresh", json={"refresh_token": one.json()["refresh_token"]}, headers=headers
        )
        assert third.status_code == 200

    async def test_an_old_token_replayed_later_kills_the_whole_session(
        self, client: AsyncClient, session: AsyncSession, test_user: User
    ):
        headers = {"X-Refresh-Mode": "body"}
        login = await client.post("/api/auth/login", data=FORM, headers=headers)
        stolen = login.json()["refresh_token"]
        rotated = await client.post("/api/auth/refresh", json={"refresh_token": stolen}, headers=headers)
        legit = rotated.json()

        # Time passes beyond the grace window.
        [row] = await _rows(session)
        row.rotated_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        await session.commit()

        replay = await client.post("/api/auth/refresh", json={"refresh_token": stolen}, headers=headers)
        assert replay.status_code == 401

        [row] = await _rows(session)
        assert row.revoked_at is not None and row.revoked_reason == "refresh_reuse"
        # The thief's copy is dead, and so is the legitimate holder's: nobody can tell them apart.
        assert (await client.get("/api/users/me", headers=_bearer(legit["access_token"]))).status_code == 401
        again = await client.post(
            "/api/auth/refresh", json={"refresh_token": legit["refresh_token"]}, headers=headers
        )
        assert again.status_code == 401

    async def test_an_idle_session_does_not_refresh(
        self, client: AsyncClient, session: AsyncSession, test_user: User
    ):
        await client.post("/api/auth/login", data=FORM)
        [row] = await _rows(session)
        row.last_refreshed_at = datetime.now(timezone.utc) - timedelta(days=get_settings().session_idle_days + 1)
        await session.commit()
        assert (await client.post("/api/auth/refresh")).status_code == 401

    async def test_a_session_ends_at_its_absolute_limit_however_active(
        self, client: AsyncClient, session: AsyncSession, test_user: User
    ):
        await client.post("/api/auth/login", data=FORM)
        [row] = await _rows(session)
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
        assert (await client.post("/api/auth/refresh")).status_code == 401

    async def test_a_deactivated_user_cannot_refresh(
        self, client: AsyncClient, session: AsyncSession, test_user: User
    ):
        await client.post("/api/auth/login", data=FORM)
        test_user.is_active = False
        session.add(test_user)
        await session.commit()
        assert (await client.post("/api/auth/refresh")).status_code == 401


@pytest.mark.asyncio
class TestSignOut:
    async def test_logout_ends_the_session_at_once(
        self, client: AsyncClient, session: AsyncSession, test_user: User
    ):
        body = await _login(client)
        headers = _bearer(body["access_token"])
        assert (await client.get("/api/users/me", headers=headers)).status_code == 200

        assert (await client.post("/api/auth/logout", headers=headers)).status_code == 200

        assert (await client.get("/api/users/me", headers=headers)).status_code == 401, "not after 15 minutes: now"
        assert (await client.post("/api/auth/refresh")).status_code == 401
        [row] = await _rows(session)
        assert row.revoked_reason == "logout"

    async def test_logout_works_with_only_the_cookie(self, client: AsyncClient, test_user: User):
        await client.post("/api/auth/login", data=FORM)
        assert (await client.post("/api/auth/logout")).status_code == 200
        assert (await client.post("/api/auth/refresh")).status_code == 401

    async def test_logout_with_nothing_is_still_fine(self, client: AsyncClient):
        assert (await client.post("/api/auth/logout")).status_code == 200


@pytest.mark.asyncio
class TestDevices:
    async def _two_devices(self, client: AsyncClient):
        first = await _login(client, **{"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/130.0"})
        second = await _login(client, **{"User-Agent": "Mozilla/5.0 (Linux; Android 16) Chrome/130.0 Mobile"})
        return first["access_token"], second["access_token"]

    async def test_the_list_shows_each_device_and_marks_this_one(self, client: AsyncClient, test_user: User):
        first, second = await self._two_devices(client)
        devices = (await client.get("/api/auth/sessions", headers=_bearer(second))).json()
        assert len(devices) == 2
        assert {d["device_label"] for d in devices} == {"Firefox em Linux", "Chrome em Android"}
        assert [d["current"] for d in devices].count(True) == 1
        assert next(d for d in devices if d["current"])["device_label"] == "Chrome em Android"
        assert all("refresh" not in key for d in devices for key in d)

    async def test_ending_another_device_takes_effect_on_its_next_request(
        self, client: AsyncClient, test_user: User
    ):
        first, second = await self._two_devices(client)
        other = next(
            d for d in (await client.get("/api/auth/sessions", headers=_bearer(second))).json() if not d["current"]
        )

        assert (await client.delete(f"/api/auth/sessions/{other['id']}", headers=_bearer(second))).status_code == 204

        assert (await client.get("/api/users/me", headers=_bearer(first))).status_code == 401
        assert (await client.get("/api/users/me", headers=_bearer(second))).status_code == 200

    async def test_revoke_all_others_keeps_this_one(self, client: AsyncClient, test_user: User):
        first, second = await self._two_devices(client)
        result = await client.post("/api/auth/sessions/revoke-others", headers=_bearer(second))
        assert result.json() == {"revoked": 1}
        assert (await client.get("/api/users/me", headers=_bearer(first))).status_code == 401
        assert (await client.get("/api/users/me", headers=_bearer(second))).status_code == 200

    async def test_nobody_can_end_someone_elses_session(
        self, client: AsyncClient, session: AsyncSession, test_user: User, test_superuser: User
    ):
        mine = (await _login(client))["access_token"]
        admin_login = await client.post(
            "/api/auth/login", data={"username": "admin@example.com", "password": "adminpass123"}
        )
        admin_session = _sid(admin_login.json()["access_token"])
        response = await client.delete(f"/api/auth/sessions/{admin_session}", headers=_bearer(mine))
        assert response.status_code == 404
        assert (
            await client.get("/api/users/me", headers=_bearer(admin_login.json()["access_token"]))
        ).status_code == 200

    async def test_the_list_needs_a_login(self, client: AsyncClient):
        assert (await client.get("/api/auth/sessions")).status_code == 401
        assert (await client.post("/api/auth/sessions/revoke-others")).status_code == 401

    async def test_revoking_is_in_the_audit_trail(
        self, client: AsyncClient, session: AsyncSession, test_user: User
    ):
        first, second = await self._two_devices(client)
        other = next(
            d for d in (await client.get("/api/auth/sessions", headers=_bearer(second))).json() if not d["current"]
        )
        await client.delete(f"/api/auth/sessions/{other['id']}", headers=_bearer(second))
        events = (
            await session.execute(select(AuditEvent).where(AuditEvent.action == "session_revoked"))
        ).scalars().all()
        assert [(e.entity_id, e.detail) for e in events] == [(other["id"], "revoked_by_user")]
        assert events[0].actor_user_id == test_user.id


@pytest.mark.asyncio
class TestPasswordChange:
    async def test_changing_the_password_ends_the_other_devices_but_not_this_one(
        self, client: AsyncClient, test_user: User
    ):
        other = (await _login(client))["access_token"]
        mine = (await _login(client))["access_token"]

        response = await client.patch(
            "/api/users/me", json={"password": "a-brand-new-pass-1"}, headers=_bearer(mine)
        )
        assert response.status_code == 200, response.text

        assert (await client.get("/api/users/me", headers=_bearer(other))).status_code == 401
        assert (await client.get("/api/users/me", headers=_bearer(mine))).status_code == 200

    async def test_a_password_reset_ends_every_session(
        self, client: AsyncClient, session: AsyncSession, test_user: User
    ):
        from app.core.auth import UserManager
        from sqlalchemy.ext.asyncio import AsyncSession as _S  # noqa: F401
        from fastapi_users.db import SQLAlchemyUserDatabase

        token = (await _login(client))["access_token"]
        manager = UserManager(SQLAlchemyUserDatabase(session, User))
        reset = manager.issue_reset_token(test_user)
        await manager.reset_password(reset, "another-new-pass-2")

        assert (await client.get("/api/users/me", headers=_bearer(token))).status_code == 401


def test_unknown_agents_get_a_generic_label():
    assert session_service.device_label(None) == "Dispositivo desconhecido"
    assert session_service.device_label("SyncroFin-Mobile/1.0 (Android 16)") == "App SyncroFin em Android"
    assert session_service.device_label("curl/8.5.0") == "curl"




@pytest.mark.asyncio
class TestAdministratorActions:
    async def _admin(self, client: AsyncClient) -> dict:
        login = await client.post(
            "/api/auth/login", data={"username": "admin@example.com", "password": "adminpass123"}
        )
        return _bearer(login.json()["access_token"])

    async def test_an_administrator_setting_a_password_signs_that_user_out(
        self, client: AsyncClient, test_user: User, test_superuser: User
    ):
        theirs = (await _login(client))["access_token"]
        admin = await self._admin(client)

        response = await client.patch(
            f"/api/admin/users/{test_user.id}", json={"password": "set-by-the-admin-1"}, headers=admin
        )
        assert response.status_code == 200, response.text

        assert (await client.get("/api/users/me", headers=_bearer(theirs))).status_code == 401
        assert (await client.get("/api/users/me", headers=admin)).status_code == 200

    async def test_deactivating_a_user_ends_their_sessions(
        self, client: AsyncClient, session: AsyncSession, test_user: User, test_superuser: User
    ):
        theirs = (await _login(client))["access_token"]
        admin = await self._admin(client)

        await client.patch(f"/api/admin/users/{test_user.id}", json={"is_active": False}, headers=admin)

        assert (await client.get("/api/users/me", headers=_bearer(theirs))).status_code == 401
        rows = [r for r in await _rows(session) if r.user_id == test_user.id]
        assert [r.revoked_reason for r in rows] == ["account_disabled"]
