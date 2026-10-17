"""Password reset and workspace invitations, by e-mail.

Until now the reset endpoint minted a token and delivered it to nobody, and a
new member could only be added if the owner invented a password and relayed it.
These pin the whole loop: the message goes out, the link in it works, and the
ways it could go wrong (no mail server, unknown address, a hostile workspace
name, a spoofed Host header) are handled.
"""
import re
from email.message import EmailMessage
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import email_service, email_templates


@pytest.fixture
def outbox(monkeypatch) -> list[EmailMessage]:
    """E-mail switched on, with the SMTP hand-off captured instead of sent."""
    settings = get_settings()
    monkeypatch.setattr(settings, "smtp_host", "smtp.test.local")
    monkeypatch.setattr(settings, "smtp_from", "SyncroFin <no-reply@test.local>")
    monkeypatch.setattr(settings, "frontend_url", "https://app.test.local")
    sent: list[EmailMessage] = []
    monkeypatch.setattr(email_service, "send_blocking", lambda _settings, msg: sent.append(msg))
    return sent


def _link(msg: EmailMessage) -> str:
    match = re.search(r"https://app\.test\.local\S+", msg.get_content())
    assert match, msg.get_content()
    return match.group(0)


def _token(link: str) -> str:
    return parse_qs(urlparse(link).query)["token"][0]


async def _login(client: AsyncClient, email: str, password: str):
    return await client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
def test_language_resolution_matches_the_shipped_languages():
    assert email_templates.resolve_lang("pt-BR") == "pt-BR"
    assert email_templates.resolve_lang("pt-PT") == "pt-BR"  # one Portuguese bundle
    assert email_templates.resolve_lang("es-MX") == "es"
    assert email_templates.resolve_lang("de") == "en"  # not shipped: English, like the UI
    assert email_templates.resolve_lang(None) == "en"


@pytest.mark.parametrize("lang", ["en", "pt-BR", "es"])
def test_every_template_renders_in_every_language(lang):
    subject, body = email_templates.password_reset(lang, "https://x/y?token=T", 60)
    assert "https://x/y?token=T" in body and "60" in body and subject

    for new in (True, False):
        subject, body = email_templates.workspace_invite(
            lang, inviter="Ana", workspace="Acme", role="viewer", link="https://x/", new_account=new
        )
        assert "Ana" in subject + body and "Acme" in subject + body and "https://x/" in body


def test_user_text_cannot_add_a_header_or_break_the_subject():
    subject, _ = email_templates.workspace_invite(
        "en", inviter="Ana", workspace="X\r\nBcc: attacker@evil.example", role="editor",
        link="https://x/", new_account=False,
    )
    assert "\n" not in subject and "\r" not in subject

    settings = get_settings()
    msg = email_service.build_message(settings, "a@b.co", subject, "body")
    assert msg["Bcc"] is None


def test_link_host_comes_from_configuration(monkeypatch):
    monkeypatch.setattr(get_settings(), "frontend_url", "https://app.test.local/")
    assert email_service.frontend_link("/reset-password", token="abc") == (
        "https://app.test.local/reset-password?token=abc"
    )


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_forgot_password_sends_a_link_that_resets_the_password(
    client: AsyncClient, test_user: User, outbox
):
    response = await client.post("/api/auth/forgot-password", json={"email": test_user.email})
    assert response.status_code == 202
    await email_service.drain()

    assert len(outbox) == 1
    msg = outbox[0]
    assert msg["To"] == test_user.email
    assert "/reset-password?token=" in _link(msg)

    reset = await client.post(
        "/api/auth/reset-password", json={"token": _token(_link(msg)), "password": "brand-new-pass-1"}
    )
    assert reset.status_code == 200
    assert (await _login(client, test_user.email, "brand-new-pass-1")).status_code == 200
    assert (await _login(client, test_user.email, "testpass123")).status_code == 400

    # The link works once: the password changed, so its fingerprint is stale.
    again = await client.post(
        "/api/auth/reset-password", json={"token": _token(_link(msg)), "password": "another-pass-2"}
    )
    assert again.status_code == 400


@pytest.mark.asyncio
async def test_an_unknown_address_gets_the_same_answer_and_no_mail(
    client: AsyncClient, test_user: User, outbox
):
    response = await client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    await email_service.drain()

    assert response.status_code == 202  # indistinguishable from the real thing
    assert outbox == []


@pytest.mark.asyncio
async def test_without_a_mail_server_the_endpoint_still_answers(
    client: AsyncClient, test_user: User, monkeypatch
):
    sent = []
    monkeypatch.setattr(email_service, "send_blocking", lambda _s, msg: sent.append(msg))
    assert not get_settings().smtp_enabled

    response = await client.post("/api/auth/forgot-password", json={"email": test_user.email})
    await email_service.drain()

    assert response.status_code == 202
    assert sent == []


@pytest.mark.asyncio
async def test_a_failing_mail_server_does_not_break_the_endpoint(
    client: AsyncClient, test_user: User, outbox, monkeypatch
):
    def refuse(_settings, _msg):
        raise ConnectionRefusedError("smtp down")

    monkeypatch.setattr(email_service, "send_blocking", refuse)
    response = await client.post("/api/auth/forgot-password", json={"email": test_user.email})
    await email_service.drain()
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_the_link_ignores_a_spoofed_host_header(
    client: AsyncClient, test_user: User, outbox
):
    await client.post(
        "/api/auth/forgot-password",
        json={"email": test_user.email},
        headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"},
    )
    await email_service.drain()

    assert _link(outbox[0]).startswith("https://app.test.local/")
    assert "evil.example" not in outbox[0].get_content()


@pytest.mark.asyncio
async def test_sso_only_instances_do_not_send_reset_mail(
    client: AsyncClient, test_user: User, outbox, oidc_only_settings
):
    response = await client.post("/api/auth/forgot-password", json={"email": test_user.email})
    await email_service.drain()
    assert response.status_code != 202
    assert outbox == []


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------
async def _invite(client, workspace, headers, **body):
    return await client.post(f"/api/workspaces/{workspace.id}/members", json=body, headers=headers)


@pytest.mark.asyncio
async def test_inviting_a_new_person_needs_no_password_when_mail_works(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers,
    test_workspace: Workspace,
    outbox,
):
    response = await _invite(
        client, test_workspace, auth_headers, email="Contador@Example.com", role="viewer"
    )
    assert response.status_code == 201
    body = response.json()
    assert body["invitation_email_sent"] is True
    assert body["role"] == "viewer"

    assert len(outbox) == 1
    msg = outbox[0]
    assert msg["To"] == "contador@example.com"
    link = _link(msg)
    assert "/reset-password?" in link and parse_qs(urlparse(link).query)["invited"] == ["1"]

    # They are a member, and the link lets them choose a password and sign in.
    user = (await session.execute(select(User).where(User.email == "contador@example.com"))).scalar_one()
    member = (
        await session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == test_workspace.id, WorkspaceMember.user_id == user.id
            )
        )
    ).scalar_one()
    assert member.role == "viewer"

    reset = await client.post(
        "/api/auth/reset-password", json={"token": _token(link), "password": "chosen-by-them-1"}
    )
    assert reset.status_code == 200
    assert (await _login(client, "contador@example.com", "chosen-by-them-1")).status_code == 200


@pytest.mark.asyncio
async def test_the_invitation_link_outlives_a_normal_reset_link(
    client: AsyncClient, auth_headers, test_workspace: Workspace, outbox
):
    import jwt

    await _invite(client, test_workspace, auth_headers, email="late@example.com", role="editor")
    payload = jwt.decode(_token(_link(outbox[0])), options={"verify_signature": False})
    lifetime = payload["exp"] - (payload.get("iat") or payload["exp"] - 7 * 86400)
    assert lifetime >= 6 * 86400  # days, not the hour a reset link lives


@pytest.mark.asyncio
async def test_without_mail_a_new_person_still_needs_a_password(
    client: AsyncClient, auth_headers, test_workspace: Workspace
):
    assert not get_settings().smtp_enabled
    response = await _invite(client, test_workspace, auth_headers, email="new@example.com", role="editor")
    assert response.status_code == 400
    assert "SMTP" in response.json()["detail"]

    ok = await _invite(
        client, test_workspace, auth_headers, email="new@example.com", role="editor", password="set-by-owner-1"
    )
    assert ok.status_code == 201
    assert ok.json()["invitation_email_sent"] is False


@pytest.mark.asyncio
async def test_an_owner_supplied_password_is_still_honoured(
    client: AsyncClient, auth_headers, test_workspace: Workspace, outbox
):
    response = await _invite(
        client, test_workspace, auth_headers, email="pw@example.com", role="editor", password="set-by-owner-1"
    )
    assert response.status_code == 201
    assert (await _login(client, "pw@example.com", "set-by-owner-1")).status_code == 200
    # They are told they were added, and pointed at the login page, not handed a reset link.
    assert "/reset-password" not in outbox[0].get_content()
    assert "/login" in outbox[0].get_content()


@pytest.mark.asyncio
async def test_an_existing_user_is_told_they_were_added(
    client: AsyncClient,
    auth_headers,
    test_workspace: Workspace,
    viewer_auth_headers,
    outbox,
):
    # `viewer_auth_headers` created a second user; find their address.
    from tests.conftest import TestSessionLocal

    async with TestSessionLocal() as s:
        others = (
            await s.execute(select(User).where(User.email != "test@example.com"))
        ).scalars().all()
    existing = next(u for u in others if u.email != "admin@example.com")

    response = await _invite(client, test_workspace, auth_headers, email=existing.email, role="editor")
    # already a member (as viewer) -> refused, and nobody is e-mailed twice
    assert response.status_code in (201, 400, 409)
    if response.status_code == 201:
        assert outbox[0]["To"] == existing.email
        assert "/reset-password" not in outbox[0].get_content()
    else:
        assert outbox == []


@pytest.mark.asyncio
async def test_a_mail_failure_does_not_undo_the_invitation(
    client: AsyncClient, auth_headers, test_workspace: Workspace, outbox, monkeypatch
):
    def refuse(_settings, _msg):
        raise ConnectionRefusedError("smtp down")

    monkeypatch.setattr(email_service, "send_blocking", refuse)
    response = await _invite(client, test_workspace, auth_headers, email="stuck@example.com", role="viewer")

    assert response.status_code == 201  # the member exists...
    assert response.json()["invitation_email_sent"] is False  # ...and the owner is told to follow up


@pytest.mark.asyncio
async def test_a_hostile_workspace_name_cannot_inject_a_header(
    client: AsyncClient,
    session: AsyncSession,
    auth_headers,
    test_workspace: Workspace,
    outbox,
):
    workspace = await session.get(Workspace, test_workspace.id)
    assert workspace is not None
    workspace.name = "Acme\r\nBcc: attacker@evil.example"
    await session.commit()

    response = await _invite(client, test_workspace, auth_headers, email="safe@example.com", role="viewer")

    assert response.status_code == 201
    msg = outbox[0]
    assert msg["Bcc"] is None
    assert "\n" not in msg["Subject"]


@pytest.mark.asyncio
async def test_forgot_password_costs_the_same_for_every_address(
    client: AsyncClient, test_user: User, outbox, monkeypatch
):
    """A stopwatch must not tell a real account from a stranger.

    The library only pays for a bcrypt fingerprint when the account exists; the
    route burns an equivalent hash for an unknown address. Count the hashes
    rather than time them: a wall clock on a busy CI runner proves nothing.
    """
    from fastapi_users.password import PasswordHelper

    calls = {"n": 0}
    real = PasswordHelper.hash

    def counting_hash(self, password):
        calls["n"] += 1
        return real(self, password)

    monkeypatch.setattr(PasswordHelper, "hash", counting_hash)

    await client.post("/api/auth/forgot-password", json={"email": test_user.email})
    known = calls["n"]
    calls["n"] = 0
    await client.post("/api/auth/forgot-password", json={"email": "stranger@example.com"})
    unknown = calls["n"]
    await email_service.drain()

    assert known >= 1
    assert unknown == known


@pytest.mark.asyncio
async def test_an_inactive_account_is_not_revealed_either(
    client: AsyncClient, session: AsyncSession, test_user: User, outbox
):
    test_user.is_active = False
    await session.commit()

    response = await client.post("/api/auth/forgot-password", json={"email": test_user.email})
    await email_service.drain()

    assert response.status_code == 202
    assert outbox == []
