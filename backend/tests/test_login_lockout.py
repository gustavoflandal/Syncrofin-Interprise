"""Lock after repeated wrong passwords, and tell the person about new devices (services/login_guard.py)."""
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from unittest.mock import patch

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_context import AuditContext, audit_context
from app.core.config import get_settings
from app.models.audit import AuditEvent
from app.models.user import User
from app.services import email_service, login_guard
from tests.test_two_factor import _make_redis_mock_with_store

PASSWORD = "testpass123"


@pytest.fixture
def outbox(monkeypatch) -> list[EmailMessage]:
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from", "SyncroFin <no-reply@test.local>")
    monkeypatch.setattr(settings, "frontend_url", "https://app.test.local")
    monkeypatch.setattr(settings, "login_max_attempts", 3)
    monkeypatch.setattr(settings, "login_lock_minutes", 15)
    sent: list[EmailMessage] = []
    monkeypatch.setattr(email_service, "send_blocking", lambda _settings, msg: sent.append(msg))
    return sent


async def _login(client: AsyncClient, email: str, password: str, **headers):
    return await client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded", **headers},
    )


async def _events(session: AsyncSession, action: str) -> list[AuditEvent]:
    return list((await session.execute(select(AuditEvent).where(AuditEvent.action == action))).scalars())


async def _user(session: AsyncSession, user: User) -> User:
    await session.refresh(user)
    return user


async def _fail(client: AsyncClient, email: str, times: int) -> None:
    for _ in range(times):
        assert (await _login(client, email, "errada-errada-1")).status_code == 400


@pytest.mark.asyncio
async def test_locks_after_the_configured_number_of_wrong_passwords(
    client: AsyncClient, session: AsyncSession, test_user: User, outbox
):
    await _fail(client, test_user.email, 3)
    await email_service.drain()

    user = await _user(session, test_user)
    assert login_guard.is_locked(user)
    assert user.lock_count == 1
    assert user.locked_until is not None
    remaining = user.locked_until - datetime.now(timezone.utc)
    assert timedelta(minutes=14) < remaining <= timedelta(minutes=15)

    # One failure event per attempt, one lock, and one notice by e-mail to the owner.
    assert len(await _events(session, "login_failed")) == 3
    assert len(await _events(session, "account_locked")) == 1
    assert [m["To"] for m in outbox] == [test_user.email]
    assert "15" in outbox[0].get_content()


@pytest.mark.asyncio
async def test_a_locked_account_refuses_even_the_right_password_and_says_nothing_different(
    client: AsyncClient, session: AsyncSession, test_user: User, outbox
):
    wrong_unknown = await _login(client, "ninguem@example.com", "errada-errada-1")
    await _fail(client, test_user.email, 3)

    blocked = await _login(client, test_user.email, PASSWORD)

    assert blocked.status_code == 400
    assert blocked.json() == wrong_unknown.json() == {"detail": "LOGIN_BAD_CREDENTIALS"}
    assert len(await _events(session, "login_blocked")) == 1


@pytest.mark.asyncio
async def test_the_lock_ends_by_itself_and_a_good_sign_in_starts_over(
    client: AsyncClient, session: AsyncSession, test_user: User, outbox
):
    await _fail(client, test_user.email, 3)
    await session.execute(
        update(User).where(User.id == test_user.id).values(locked_until=datetime.now(timezone.utc) - timedelta(seconds=1))
    )
    await session.commit()

    assert (await _login(client, test_user.email, PASSWORD)).status_code == 200
    user = await _user(session, test_user)
    assert (user.failed_login_count, user.lock_count, user.locked_until) == (0, 0, None)


@pytest.mark.asyncio
async def test_each_new_lock_lasts_twice_as_long_up_to_an_hour():
    settings = get_settings()
    base = settings.login_lock_minutes
    assert login_guard.lock_duration(0) == timedelta(minutes=base)
    assert login_guard.lock_duration(1) == timedelta(minutes=base * 2)
    assert login_guard.lock_duration(2) == timedelta(minutes=base * 4)
    # However many times, it never lasts longer than an hour, and never overflows.
    assert login_guard.lock_duration(3) == timedelta(hours=1)
    assert login_guard.lock_duration(10_000) == timedelta(hours=1)


@pytest.mark.asyncio
async def test_a_good_password_in_between_resets_the_count(
    client: AsyncClient, session: AsyncSession, test_user: User, outbox
):
    await _fail(client, test_user.email, 2)
    assert (await _login(client, test_user.email, PASSWORD)).status_code == 200
    await _fail(client, test_user.email, 2)

    assert not login_guard.is_locked(await _user(session, test_user))


@pytest.mark.asyncio
async def test_unknown_addresses_leave_a_trail_and_lock_nothing(
    client: AsyncClient, session: AsyncSession, test_user: User, outbox
):
    await _fail(client, "ninguem@example.com", 4)

    events = await _events(session, "login_failed")
    assert len(events) == 4
    assert {e.detail for e in events} == {"unknown_user"}
    assert all(e.changes is None for e in events)  # what was typed is not kept
    assert outbox == []


@pytest.mark.asyncio
async def test_wrong_authenticator_codes_count_toward_the_same_lock(
    client: AsyncClient, session: AsyncSession, test_user: User, outbox
):
    store = _make_redis_mock_with_store()

    async def _fake():
        return store

    with patch("app.api.custom_auth.get_redis", _fake), patch("app.api.two_factor.get_redis", _fake):
        await _second_factor_run(client, session, test_user)


async def _second_factor_run(client: AsyncClient, session: AsyncSession, test_user: User) -> None:
    secret = pyotp.random_base32()
    await session.execute(update(User).where(User.id == test_user.id).values(totp_secret=secret, is_2fa_enabled=True))
    await session.commit()

    challenge = (await _login(client, test_user.email, PASSWORD)).json()
    assert challenge["requires_2fa"] is True
    for _ in range(3):
        wrong = await client.post(
            "/api/auth/2fa/verify", json={"temp_token": challenge["temp_token"], "code": "000000"}
        )
        assert wrong.status_code == 400, wrong.text
    assert login_guard.is_locked(await _user(session, test_user))

    # Locked: not even the right code is taken.
    right = await client.post(
        "/api/auth/2fa/verify", json={"temp_token": challenge["temp_token"], "code": pyotp.TOTP(secret).now()}
    )
    assert right.status_code == 401
    assert {e.detail for e in await _events(session, "login_failed")} == {"bad_2fa_code"}


@pytest.mark.asyncio
async def test_an_administrator_can_lift_the_lock(
    client: AsyncClient, session: AsyncSession, test_user: User, admin_auth_headers: dict, outbox
):
    await _fail(client, test_user.email, 3)

    lifted = await client.post(f"/api/admin/users/{test_user.id}/unlock", headers=admin_auth_headers)
    assert lifted.status_code == 204
    assert not login_guard.is_locked(await _user(session, test_user))
    assert (await _login(client, test_user.email, PASSWORD)).status_code == 200
    unlocked = await _events(session, "account_unlocked")
    assert len(unlocked) == 1 and unlocked[0].detail == "admin"

    listing = await client.get("/api/admin/users", headers=admin_auth_headers)
    assert listing.status_code == 200 and "locked_until" in listing.json()["items"][0]


@pytest.mark.asyncio
async def test_only_an_administrator_can_unlock(client: AsyncClient, test_user: User, auth_headers: dict):
    response = await client.post(f"/api/admin/users/{test_user.id}/unlock", headers=auth_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_resetting_the_password_lifts_the_lock(
    client: AsyncClient, session: AsyncSession, test_user: User, outbox
):
    await _fail(client, test_user.email, 3)
    token = (await _user(session, test_user)) and _reset_token(test_user)

    reset = await client.post("/api/auth/reset-password", json={"token": token, "password": "uma-senha-nova-e-longa"})
    assert reset.status_code == 200
    assert (await _login(client, test_user.email, "uma-senha-nova-e-longa")).status_code == 200


def _reset_token(user: User) -> str:
    from fastapi_users.db import SQLAlchemyUserDatabase

    from app.core.auth import UserManager

    return UserManager(SQLAlchemyUserDatabase(None, User)).issue_reset_token(user)  # ty: ignore[invalid-argument-type]


@pytest.mark.asyncio
async def test_a_new_device_gets_an_e_mail_but_the_first_sign_in_and_known_devices_do_not(
    client: AsyncClient, test_user: User, outbox
):
    chrome = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0 Safari/537.36"}
    firefox = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"}

    assert (await _login(client, test_user.email, PASSWORD, **chrome)).status_code == 200
    await email_service.drain()
    assert outbox == []  # the first sign-in ever is not news

    assert (await _login(client, test_user.email, PASSWORD, **chrome)).status_code == 200
    await email_service.drain()
    assert outbox == []  # the same browser and system again

    assert (await _login(client, test_user.email, PASSWORD, **firefox)).status_code == 200
    await email_service.drain()
    assert len(outbox) == 1
    body = outbox[0].get_content()
    assert "Firefox em Linux" in body
    assert "https://app.test.local" in body


@pytest.mark.asyncio
async def test_wrong_password_when_turning_off_2fa_counts_toward_the_lock(
    client: AsyncClient, session: AsyncSession, test_user: User, auth_headers: dict, outbox
):
    await session.execute(update(User).where(User.id == test_user.id).values(totp_secret=pyotp.random_base32(), is_2fa_enabled=True))
    await session.commit()

    for _ in range(3):
        wrong = await client.post("/api/auth/2fa/disable", json={"password": "errada-errada-1", "code": "000000"}, headers=auth_headers)
        assert wrong.status_code == 400
    assert login_guard.is_locked(await _user(session, test_user))
    assert {e.detail for e in await _events(session, "login_failed")} == {"bad_password"}


@pytest.mark.asyncio
async def test_the_cli_can_unlock_an_account(client: AsyncClient, session: AsyncSession, test_user: User, outbox, monkeypatch):
    from app import cli

    await _fail(client, test_user.email, 3)
    assert login_guard.is_locked(await _user(session, test_user))

    await cli.unlock_user(test_user.email)

    assert not login_guard.is_locked(await _user(session, test_user))
    assert [e.detail for e in await _events(session, "account_unlocked")] == ["cli"]


@pytest.mark.asyncio
async def test_a_lock_set_by_an_overlapping_guess_is_attributed_to_the_person(
    session: AsyncSession, test_user: User, outbox
):
    """The lock appears in the database after the first look-up and before the answer: the event that says
    so belongs to the person's own history like its siblings."""
    from types import SimpleNamespace

    class Manager:
        password_helper = SimpleNamespace(verify_and_update=lambda *_: (True, None))

        async def get_by_email(self, email):
            return test_user

        async def authenticate(self, credentials):
            await session.execute(
                update(User)
                .where(User.id == test_user.id)
                .values(locked_until=datetime.now(timezone.utc) + timedelta(minutes=5))
                .execution_options(synchronize_session=False)
            )
            return test_user

    credentials = SimpleNamespace(username=test_user.email, password=PASSWORD)
    marker = audit_context.set(AuditContext())
    try:
        assert await login_guard.authenticate(session, Manager(), credentials) is None
    finally:
        audit_context.reset(marker)

    [blocked] = await _events(session, "login_blocked")
    assert blocked.actor_user_id == test_user.id
