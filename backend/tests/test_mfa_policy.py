"""The second-factor rule: switched on by an administrator, enforced per session."""
from unittest.mock import patch

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.audit import AuditEvent
from app.models.user import User
from app.models.user_session import UserSession
from app.services import mfa_policy
from tests.conftest import issue_test_token
from tests.test_two_factor import _make_redis_mock_with_store

USER_FORM = {"username": "test@example.com", "password": "testpass123"}
ADMIN_FORM = {"username": "admin@example.com", "password": "adminpass123"}


@pytest.fixture
def fake_redis(_mock_redis):
    """The 2FA challenge lives in Redis: give the login and verify routes a store that remembers."""
    mock = _make_redis_mock_with_store()

    async def _fake():
        return mock

    with patch("app.core.redis.get_redis", _fake),          patch("app.core.rate_limit.get_redis", _fake),          patch("app.api.custom_auth.get_redis", _fake),          patch("app.api.two_factor.get_redis", _fake):
        yield mock


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _admin(user: User, *, verified: bool = True) -> dict:
    """An administrator's headers, with a session that already holds a second factor by default."""
    return _bearer(await issue_test_token(user, mfa_verified=verified, method="2fa" if verified else "password"))


async def _set(client: AsyncClient, admin: dict, key: str, value: str):
    return await client.patch(f"/api/admin/settings/{key}", json={"value": value}, headers=admin)


async def _require(client: AsyncClient, admin: dict, *, grace: str = "0", scope: str = "all") -> None:
    assert (await _set(client, admin, "mfa_grace_days", grace)).status_code == 200
    assert (await _set(client, admin, "mfa_required_scope", scope)).status_code == 200
    response = await _set(client, admin, "mfa_required", "true")
    assert response.status_code == 200, response.text


async def _password_session(client: AsyncClient) -> dict:
    response = await client.post("/api/auth/login", data=USER_FORM)
    assert response.status_code == 200, response.text
    return _bearer(response.json()["access_token"])


@pytest.mark.asyncio
class TestOff:
    async def test_by_default_nothing_is_asked(self, client: AsyncClient, test_user: User):
        headers = await _password_session(client)
        assert (await client.get("/api/accounts", headers=headers)).status_code == 200
        status = (await client.get("/api/auth/mfa-status", headers=headers)).json()
        assert status["applies"] is False and status["blocked"] is False and status["reminder"] is False


@pytest.mark.asyncio
class TestEnforced:
    async def test_a_password_session_can_only_enrol(
        self, client: AsyncClient, test_user: User, test_superuser: User
    ):
        await _require(client, await _admin(test_superuser))
        headers = await _password_session(client)

        blocked = await client.get("/api/accounts", headers=headers)
        assert blocked.status_code == 403 and blocked.json()["detail"] == "MFA_ENROLLMENT_REQUIRED"

        # ...but the way out is open.
        assert (await client.get("/api/users/me", headers=headers)).status_code == 200
        status = (await client.get("/api/auth/mfa-status", headers=headers)).json()
        assert status["blocked"] is True and status["enrolled"] is False
        assert (await client.post("/api/auth/2fa/setup", headers=headers)).status_code == 200
        assert (await client.get("/api/auth/sessions", headers=headers)).status_code == 200

    async def test_enrolling_lets_the_same_session_in(
        self, client: AsyncClient, session: AsyncSession, test_user: User, test_superuser: User
    ):
        await _require(client, await _admin(test_superuser))
        headers = await _password_session(client)

        secret = (await client.post("/api/auth/2fa/setup", headers=headers)).json()["secret"]
        # A wrong code proves nothing.
        wrong = await client.post("/api/auth/2fa/enable", json={"code": "000000"}, headers=headers)
        assert wrong.status_code == 400
        assert (await client.get("/api/accounts", headers=headers)).status_code == 403

        ok = await client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=headers)
        assert ok.status_code == 200
        assert (await client.get("/api/accounts", headers=headers)).status_code == 200
        status = (await client.get("/api/auth/mfa-status", headers=headers)).json()
        assert status["blocked"] is False and status["session_verified"] is True

    async def test_the_next_sign_in_asks_for_the_code_and_is_verified(
        self, client: AsyncClient, fake_redis, test_user: User, test_superuser: User
    ):
        await _require(client, await _admin(test_superuser))
        headers = await _password_session(client)
        secret = (await client.post("/api/auth/2fa/setup", headers=headers)).json()["secret"]
        await client.post("/api/auth/2fa/enable", json={"code": pyotp.TOTP(secret).now()}, headers=headers)

        login = (await client.post("/api/auth/login", data=USER_FORM)).json()
        assert login["requires_2fa"] is True
        verified = await client.post(
            "/api/auth/2fa/verify", json={"temp_token": login["temp_token"], "code": pyotp.TOTP(secret).now()}
        )
        token = verified.json()["access_token"]
        assert (await client.get("/api/accounts", headers=_bearer(token))).status_code == 200

    async def test_a_passkey_or_company_login_carries_its_own_second_factor(
        self, client: AsyncClient, test_user: User, test_superuser: User
    ):
        await _require(client, await _admin(test_superuser))
        for method in ("passkey", "oidc", "2fa"):
            token = await issue_test_token(test_user, mfa_verified=True, method=method)
            assert (await client.get("/api/accounts", headers=_bearer(token))).status_code == 200, method

    async def test_the_admin_routes_are_held_back_too(
        self, client: AsyncClient, test_user: User, test_superuser: User
    ):
        await _require(client, await _admin(test_superuser))
        unverified_admin = await _admin(test_superuser, verified=False)
        assert (await client.get("/api/admin/users", headers=unverified_admin)).status_code == 403

    async def test_a_session_that_ends_is_not_a_way_around_it(
        self, client: AsyncClient, test_user: User, test_superuser: User
    ):
        await _require(client, await _admin(test_superuser))
        headers = await _password_session(client)
        await client.post("/api/auth/logout", headers=headers)
        assert (await client.get("/api/users/me", headers=headers)).status_code == 401


@pytest.mark.asyncio
class TestGracePeriod:
    async def test_during_the_grace_period_people_are_reminded_not_blocked(
        self, client: AsyncClient, test_user: User, test_superuser: User
    ):
        await _require(client, await _admin(test_superuser), grace="7")
        headers = await _password_session(client)

        assert (await client.get("/api/accounts", headers=headers)).status_code == 200
        status = (await client.get("/api/auth/mfa-status", headers=headers)).json()
        assert status["reminder"] is True and status["blocked"] is False and status["enforced"] is False
        assert status["enforced_from"] is not None

    async def test_when_the_date_arrives_the_rule_is_in_force(
        self, client: AsyncClient, session: AsyncSession, test_user: User, test_superuser: User
    ):
        await _require(client, await _admin(test_superuser), grace="7")
        headers = await _password_session(client)
        assert (await client.get("/api/accounts", headers=headers)).status_code == 200

        past = "2020-01-01T00:00:00+00:00"
        from app.services.admin_service import set_app_setting

        await set_app_setting(session, "mfa_enforced_from", past)
        assert (await client.get("/api/accounts", headers=headers)).status_code == 403


@pytest.mark.asyncio
class TestScope:
    async def test_only_administrators(self, client: AsyncClient, test_user: User, test_superuser: User):
        await _require(client, await _admin(test_superuser), scope="admins")

        assert (await client.get("/api/accounts", headers=await _password_session(client))).status_code == 200
        unverified_admin = await _admin(test_superuser, verified=False)
        assert (await client.get("/api/admin/users", headers=unverified_admin)).status_code == 403


@pytest.mark.asyncio
class TestTurningItOn:
    async def test_an_administrator_without_a_second_factor_cannot_switch_it_on(
        self, client: AsyncClient, test_superuser: User
    ):
        """Otherwise the next request would already be held back and nobody could switch it off."""
        response = await _set(client, await _admin(test_superuser, verified=False), "mfa_required", "true")
        assert response.status_code == 400 and response.json()["detail"] == "MFA_ADMIN_NOT_ENROLLED"

    async def test_bad_values_are_refused(self, client: AsyncClient, test_superuser: User):
        admin = await _admin(test_superuser)
        assert (await _set(client, admin, "mfa_required", "maybe")).status_code == 400
        assert (await _set(client, admin, "mfa_required_scope", "everyone")).status_code == 400
        assert (await _set(client, admin, "mfa_grace_days", "-1")).status_code == 400
        assert (await _set(client, admin, "mfa_grace_days", "9999")).status_code == 400
        assert (await _set(client, admin, "mfa_grace_days", "abc")).status_code == 400

    async def test_switching_it_off_forgets_the_date(self, client: AsyncClient, test_superuser: User):
        admin = await _admin(test_superuser)
        await _require(client, admin, grace="7")
        await _set(client, admin, "mfa_required", "false")
        overview = (await client.get("/api/admin/mfa-policy", headers=admin)).json()
        assert overview["required"] is False and overview["enforced_from"] is None

    async def test_the_overview_counts_who_would_be_held_back(
        self, client: AsyncClient, test_user: User, test_superuser: User
    ):
        admin = await _admin(test_superuser)
        overview = (await client.get("/api/admin/mfa-policy", headers=admin)).json()
        assert overview["users_total"] == 2 and overview["users_without_2fa"] == 2
        assert overview["from_environment"] is False

    async def test_only_administrators_see_or_change_the_rule(self, client: AsyncClient, test_user: User):
        headers = _bearer(await issue_test_token(test_user))
        assert (await client.get("/api/admin/mfa-policy", headers=headers)).status_code == 403
        assert (await _set(client, headers, "mfa_required", "true")).status_code == 403

    async def test_the_change_is_in_the_audit_trail(
        self, client: AsyncClient, session: AsyncSession, test_user: User, test_superuser: User
    ):
        await _require(client, await _admin(test_superuser))
        events = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.entity_type == "app_settings", AuditEvent.entity_id == "mfa_required")
            )
        ).scalars().all()
        assert events and events[0].actor_user_id == test_superuser.id


@pytest.mark.asyncio
class TestEnvironment:
    async def test_require_mfa_in_the_environment_is_immediate_and_the_panel_cannot_lift_it(
        self, client: AsyncClient, test_user: User, test_superuser: User
    ):
        settings = get_settings()
        settings.require_mfa = True
        try:
            headers = await _password_session(client)
            assert (await client.get("/api/accounts", headers=headers)).status_code == 403

            admin = await _admin(test_superuser)
            await _set(client, admin, "mfa_required", "false")
            assert (await client.get("/api/accounts", headers=headers)).status_code == 403
            overview = (await client.get("/api/admin/mfa-policy", headers=admin)).json()
            assert overview["from_environment"] is True and overview["required"] is True
        finally:
            settings.require_mfa = False


@pytest.mark.asyncio
class TestAdministratorReset:
    async def test_a_lost_phone_is_reset_by_an_administrator(
        self, client: AsyncClient, session: AsyncSession, test_user: User, test_superuser: User
    ):
        test_user.totp_secret = pyotp.random_base32()
        test_user.is_2fa_enabled = True
        session.add(test_user)
        await session.commit()
        theirs = _bearer(await issue_test_token(test_user, mfa_verified=True, method="2fa"))
        admin = await _admin(test_superuser)

        response = await client.post(f"/api/admin/users/{test_user.id}/reset-2fa", headers=admin)
        assert response.status_code == 204

        await session.refresh(test_user)
        assert test_user.is_2fa_enabled is False and test_user.totp_secret is None
        assert (await client.get("/api/users/me", headers=theirs)).status_code == 401, "their sessions ended"
        login = await client.post("/api/auth/login", data=USER_FORM)
        assert "access_token" in login.json(), "the password alone signs in again"

    async def test_not_for_yourself_not_for_the_unknown_not_for_the_ordinary(
        self, client: AsyncClient, test_user: User, test_superuser: User
    ):
        admin = await _admin(test_superuser)
        assert (await client.post(f"/api/admin/users/{test_superuser.id}/reset-2fa", headers=admin)).status_code == 400
        assert (
            await client.post("/api/admin/users/00000000-0000-0000-0000-000000000000/reset-2fa", headers=admin)
        ).status_code == 404
        theirs = _bearer(await issue_test_token(test_user))
        assert (await client.post(f"/api/admin/users/{test_superuser.id}/reset-2fa", headers=theirs)).status_code == 403

    async def test_the_admin_list_shows_who_has_a_second_factor(
        self, client: AsyncClient, session: AsyncSession, test_user: User, test_superuser: User
    ):
        test_user.is_2fa_enabled = True
        session.add(test_user)
        await session.commit()
        users = (await client.get("/api/admin/users", headers=await _admin(test_superuser))).json()["items"]
        assert {u["email"]: u["is_2fa_enabled"] for u in users} == {
            "test@example.com": True,
            "admin@example.com": False,
        }


class TestRouteAllowlist:
    def test_the_enrolment_routes_are_exactly_these(self):
        assert mfa_policy.is_enrolment_route("GET", "/api/users/me")
        assert mfa_policy.is_enrolment_route("POST", "/api/auth/2fa/setup")
        assert mfa_policy.is_enrolment_route("DELETE", "/api/auth/sessions/3f0c6a52-7d1e-4c9a-9a0e-2a5b6c1d9e11")

    def test_nothing_else_is_open(self):
        assert not mfa_policy.is_enrolment_route("GET", "/api/accounts")
        assert not mfa_policy.is_enrolment_route("PATCH", "/api/users/me")
        assert not mfa_policy.is_enrolment_route("GET", "/api/admin/users")
        assert not mfa_policy.is_enrolment_route("POST", "/api/auth/2fa/disable")
        assert not mfa_policy.is_enrolment_route("GET", "/api/auth/sessions/abc"), "only DELETE by id"


@pytest.mark.asyncio
async def test_sessions_carry_the_flag_from_how_they_were_opened(
    client: AsyncClient, session: AsyncSession, test_user: User
):
    await client.post("/api/auth/login", data=USER_FORM)
    rows = (await session.execute(select(UserSession).execution_options(populate_existing=True))).scalars().all()
    assert [(r.auth_method, r.mfa_verified) for r in rows] == [("password", False)]
