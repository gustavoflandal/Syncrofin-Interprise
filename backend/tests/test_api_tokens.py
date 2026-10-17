"""API tokens: made once, limited to a workspace and to scopes, and never more than their owner can do."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_token import ApiToken
from app.models.audit import AuditEvent
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import api_token_service
from tests.conftest import issue_test_token

pytestmark = pytest.mark.asyncio


def _bearer(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


async def _make(client: AsyncClient, headers: dict, *, name: str = "Integração", scopes=None, days: int = 30) -> dict:
    response = await client.post(
        "/api/api-tokens", json={"name": name, "scopes": scopes or ["export.read"], "days": days}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _member(session: AsyncSession, workspace: Workspace, role: str) -> tuple[User, dict]:
    user = User(
        id=uuid.uuid4(),
        email=f"{role.replace('_', '-')}-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=workspace.id, user_id=user.id, role=role))
    await session.commit()
    return user, {"Authorization": f"Bearer {await issue_test_token(user)}", "X-Workspace-Id": str(workspace.id)}


async def _account_in(session: AsyncSession, workspace: Workspace, owner: User):
    from app.models.account import Account

    account = Account(id=uuid.uuid4(), user_id=owner.id, workspace_id=workspace.id, name="Caixa", type="checking", currency="BRL")
    session.add(account)
    await session.commit()
    return account


def _transaction(account_id) -> dict:
    return {"description": "Papel A4", "amount": "25.00", "date": "2026-09-10", "type": "debit", "account_id": str(account_id)}


class TestMakingAToken:
    async def test_the_secret_is_shown_once_and_only_its_hash_is_kept(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict
    ):
        created = await _make(client, auth_headers)
        secret = created["token"]
        assert secret.startswith("sfn_")
        prefix = created["item"]["prefix"]
        assert prefix.startswith("sfn_") and len(prefix) == 12 and secret.startswith(prefix + "_")

        row = (await session.execute(select(ApiToken))).scalars().one()
        assert row.token_hash == api_token_service.hash_token(secret)
        assert secret not in (row.token_hash, row.prefix, row.name)

        listed = (await client.get("/api/api-tokens", headers=auth_headers)).json()
        assert secret not in str(listed), "nothing that lists tokens can show the secret again"
        assert listed[0]["prefix"] == created["item"]["prefix"] and listed[0]["state"] == "active"

    async def test_it_expires_when_asked_and_never_lasts_forever(self, client: AsyncClient, auth_headers: dict):
        created = await _make(client, auth_headers, days=10)
        expires = datetime.fromisoformat(created["item"]["expires_at"])
        assert timedelta(days=9, hours=23) < expires - datetime.now(timezone.utc) < timedelta(days=10, minutes=1)
        for days in (0, 366, -5):
            response = await client.post(
                "/api/api-tokens", json={"name": "x", "scopes": ["export.read"], "days": days}, headers=auth_headers
            )
            assert response.status_code == 422, days

    async def test_bad_scopes_are_refused(self, client: AsyncClient, auth_headers: dict):
        def post(scopes):
            return client.post("/api/api-tokens", json={"name": "x", "scopes": scopes}, headers=auth_headers)

        assert (await post([])).status_code == 400
        assert (await post(["fly.moon"])).status_code == 400
        # A credential that lives in a script cannot invite people, make roles, or make more tokens.
        for admin in ("members.manage", "roles.manage", "workspace.manage", "tokens.manage"):
            refused = await post([admin])
            assert refused.status_code == 400 and "administrative" in refused.json()["detail"], admin

    async def test_a_token_needs_a_name(self, client: AsyncClient, auth_headers: dict):
        response = await client.post("/api/api-tokens", json={"name": "   ", "scopes": ["export.read"]}, headers=auth_headers)
        assert response.status_code in (400, 422)

    async def test_only_someone_with_the_permission_can_make_or_see_tokens(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace
    ):
        _, editor = await _member(session, test_workspace, "editor")
        assert (await client.get("/api/api-tokens", headers=editor)).status_code == 403
        assert (await client.post("/api/api-tokens", json={"name": "x", "scopes": ["export.read"]}, headers=editor)).status_code == 403

    async def test_a_token_cannot_carry_more_than_its_maker_can_do(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, auth_headers: dict
    ):
        role = (
            await client.post(
                "/api/roles", json={"name": "Integrador", "permissions": ["tokens.manage", "export.read"]}, headers=auth_headers
            )
        ).json()
        _, integrator = await _member(session, test_workspace, role["key"])

        fine = await client.post("/api/api-tokens", json={"name": "ok", "scopes": ["export.read"]}, headers=integrator)
        assert fine.status_code == 201
        beyond = await client.post("/api/api-tokens", json={"name": "no", "scopes": ["transactions.write"]}, headers=integrator)
        assert beyond.status_code == 403 and "transactions.write" in beyond.json()["detail"]

    async def test_creating_a_token_is_audited_without_the_secret(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict
    ):
        created = await _make(client, auth_headers)
        events = (
            await session.execute(select(AuditEvent).where(AuditEvent.entity_type == "api_tokens"))
        ).scalars().all()
        assert [e.action for e in events] == ["create"]
        assert events[0].changes is not None
        assert events[0].changes["token_hash"] == [None, "***"]
        assert created["token"] not in str(events[0].changes)

    async def test_there_is_a_limit_of_active_tokens_per_workspace(
        self, client: AsyncClient, auth_headers: dict, monkeypatch
    ):
        monkeypatch.setattr(api_token_service, "MAX_TOKENS_PER_WORKSPACE", 2)
        await _make(client, auth_headers, name="um")
        await _make(client, auth_headers, name="dois")
        response = await client.post("/api/api-tokens", json={"name": "três", "scopes": ["export.read"]}, headers=auth_headers)
        assert response.status_code == 400 and "At most" in response.json()["detail"]


class TestUsingAToken:
    async def test_a_read_token_reads_and_exports_but_cannot_write(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, test_user: User, auth_headers: dict
    ):
        account = await _account_in(session, test_workspace, test_user)
        secret = (await _make(client, auth_headers, scopes=["export.read"]))["token"]

        assert (await client.get("/api/accounts", headers=_bearer(secret))).status_code == 200
        assert (await client.post("/api/export/backup", json={}, headers=_bearer(secret))).status_code == 200
        blocked = await client.post("/api/transactions", json=_transaction(account.id), headers=_bearer(secret))
        assert blocked.status_code == 403 and "transactions.write" in blocked.json()["detail"]

    async def test_a_write_token_writes_only_what_it_was_given(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, test_user: User, auth_headers: dict
    ):
        account = await _account_in(session, test_workspace, test_user)
        secret = (await _make(client, auth_headers, scopes=["transactions.write"]))["token"]

        assert (await client.post("/api/transactions", json=_transaction(account.id), headers=_bearer(secret))).status_code == 201
        # Not the categories, not the export, not the audit trail.
        assert (await client.post("/api/categories", json={"name": "x", "icon": "tag", "color": "#112233"}, headers=_bearer(secret))).status_code == 403
        assert (await client.post("/api/export/backup", json={}, headers=_bearer(secret))).status_code == 403
        assert (await client.get("/api/audit", headers=_bearer(secret))).status_code == 403

    async def test_what_a_token_does_is_attributed_to_it_in_the_audit_trail(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, test_user: User, auth_headers: dict
    ):
        account = await _account_in(session, test_workspace, test_user)
        created = await _make(client, auth_headers, scopes=["transactions.write"])
        response = await client.post("/api/transactions", json=_transaction(account.id), headers=_bearer(created["token"]))
        tx_id = response.json()["id"]

        events = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.entity_type == "transactions", AuditEvent.entity_id == tx_id)
            )
        ).scalars().all()
        assert events and {e.actor_kind for e in events} == {"api_token"}
        assert {e.actor_user_id for e in events} == {test_user.id}, "the person behind the token"
        assert {e.detail for e in events} == {f"api_token:{created['item']['prefix']}"}, "and which token it was"

    async def test_the_token_stays_in_its_workspace(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, test_user: User, auth_headers: dict
    ):
        other = Workspace(id=uuid.uuid4(), name="Outro", kind="business", created_by_user_id=test_user.id)
        session.add(other)
        await session.flush()
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=other.id, user_id=test_user.id, role="owner"))
        await session.commit()
        secret = (await _make(client, auth_headers))["token"]

        assert (await client.get("/api/accounts", headers={**_bearer(secret), "X-Workspace-Id": str(other.id)})).status_code == 403
        assert (await client.get("/api/accounts", headers={**_bearer(secret), "X-Workspace-Id": str(test_workspace.id)})).status_code == 200
        current = (await client.get("/api/workspaces/current", headers=_bearer(secret))).json()
        assert current["id"] == str(test_workspace.id), "with no header it is still its own workspace"
        assert current["permissions"] == ["export.read"], "and it sees only what it may do"

    async def test_a_token_is_refused_wherever_the_route_is_about_the_person(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, test_superuser: User
    ):
        # The token of an administrator, of all people.
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=test_superuser.id, role="owner"))
        await session.commit()
        admin = {"Authorization": f"Bearer {await issue_test_token(test_superuser)}", "X-Workspace-Id": str(test_workspace.id)}
        secret = (await _make(client, admin))["token"]

        for path in ("/api/users/me", "/api/auth/sessions", "/api/admin/users", "/api/workspaces", "/api/auth/mfa-status"):
            response = await client.get(path, headers=_bearer(secret))
            assert response.status_code == 403, path
        assert (await client.get("/api/accounts", headers=_bearer(secret))).status_code == 200

    async def test_a_token_cannot_manage_tokens(self, client: AsyncClient, auth_headers: dict):
        created = await _make(client, auth_headers)
        secret = created["token"]

        assert (await client.get("/api/api-tokens", headers=_bearer(secret))).status_code == 403
        assert (await client.post("/api/api-tokens", json={"name": "x", "scopes": ["export.read"]}, headers=_bearer(secret))).status_code == 403
        assert (await client.post(f"/api/api-tokens/{created['item']['id']}/rotate", headers=_bearer(secret))).status_code == 403
        assert (await client.delete(f"/api/api-tokens/{created['item']['id']}", headers=_bearer(secret))).status_code == 403

    async def test_using_it_records_when(self, client: AsyncClient, session: AsyncSession, auth_headers: dict):
        secret = (await _make(client, auth_headers))["token"]
        assert (await session.execute(select(ApiToken.last_used_at))).scalar_one() is None

        await client.get("/api/accounts", headers=_bearer(secret))

        session.expire_all()
        assert (await session.execute(select(ApiToken.last_used_at))).scalar_one() is not None

    async def test_garbage_is_refused(self, client: AsyncClient, test_user: User):
        for bad in ("sfn_", "sfn_deadbeef_notarealsecret", "sfn_" + "a" * 60):
            assert (await client.get("/api/accounts", headers=_bearer(bad))).status_code == 401, bad


class TestWhenATokenStopsWorking:
    async def test_revoking_ends_it_at_once(self, client: AsyncClient, auth_headers: dict):
        created = await _make(client, auth_headers)
        secret = created["token"]
        assert (await client.get("/api/accounts", headers=_bearer(secret))).status_code == 200

        assert (await client.delete(f"/api/api-tokens/{created['item']['id']}", headers=auth_headers)).status_code == 204

        assert (await client.get("/api/accounts", headers=_bearer(secret))).status_code == 401
        listed = (await client.get("/api/api-tokens", headers=auth_headers)).json()
        assert listed[0]["state"] == "revoked" and listed[0]["revoked_at"]

    async def test_an_expired_token_does_not_work(self, client: AsyncClient, session: AsyncSession, auth_headers: dict):
        created = await _make(client, auth_headers)
        await session.execute(update(ApiToken).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await session.commit()

        assert (await client.get("/api/accounts", headers=_bearer(created["token"]))).status_code == 401
        assert (await client.get("/api/api-tokens", headers=auth_headers)).json()[0]["state"] == "expired"

    async def test_demoting_its_owner_shrinks_the_token_at_once(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, test_user: User, auth_headers: dict
    ):
        role = (
            await client.post(
                "/api/roles",
                json={"name": "Lançador com tokens", "permissions": ["tokens.manage", "transactions.write", "export.read"]},
                headers=auth_headers,
            )
        ).json()
        owner_of_token, headers = await _member(session, test_workspace, role["key"])
        account = await _account_in(session, test_workspace, test_user)
        created = await _make(client, headers, scopes=["transactions.write", "export.read"])
        secret = created["token"]
        assert (await client.post("/api/transactions", json=_transaction(account.id), headers=_bearer(secret))).status_code == 201

        # The role loses the permission to write.
        await client.patch(f"/api/roles/{role['id']}", json={"permissions": ["tokens.manage", "export.read"]}, headers=auth_headers)

        assert (await client.post("/api/transactions", json=_transaction(account.id), headers=_bearer(secret))).status_code == 403
        assert (await client.post("/api/export/backup", json={}, headers=_bearer(secret))).status_code == 200
        assert owner_of_token.id

    async def test_removing_the_person_from_the_workspace_ends_their_tokens(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, auth_headers: dict
    ):
        role = (
            await client.post("/api/roles", json={"name": "Integrador", "permissions": ["tokens.manage", "export.read"]}, headers=auth_headers)
        ).json()
        user, headers = await _member(session, test_workspace, role["key"])
        secret = (await _make(client, headers))["token"]
        assert (await client.get("/api/accounts", headers=_bearer(secret))).status_code == 200

        removed = await client.delete(f"/api/workspaces/{test_workspace.id}/members/{user.id}", headers=auth_headers)
        assert removed.status_code == 204

        assert (await client.get("/api/accounts", headers=_bearer(secret))).status_code in (401, 404)

    async def test_deactivating_the_person_ends_their_tokens(
        self, client: AsyncClient, session: AsyncSession, auth_headers: dict, test_user: User
    ):
        secret = (await _make(client, auth_headers))["token"]
        test_user.is_active = False
        session.add(test_user)
        await session.commit()

        assert (await client.get("/api/accounts", headers=_bearer(secret))).status_code == 401


class TestRotatingAndRevoking:
    async def test_rotating_gives_a_new_secret_and_ends_the_old_one(self, client: AsyncClient, auth_headers: dict):
        created = await _make(client, auth_headers, name="Cobrança", scopes=["export.read", "invoices.write"], days=60)
        old, new_id = created["token"], created["item"]["id"]

        rotated = (await client.post(f"/api/api-tokens/{new_id}/rotate", headers=auth_headers)).json()

        assert rotated["token"] != old
        assert rotated["item"]["name"] == "Cobrança" and rotated["item"]["scopes"] == ["export.read", "invoices.write"]
        lifetime = datetime.fromisoformat(rotated["item"]["expires_at"]) - datetime.fromisoformat(rotated["item"]["created_at"])
        assert timedelta(days=59, hours=23) < lifetime < timedelta(days=60, minutes=1)
        assert (await client.get("/api/accounts", headers=_bearer(old))).status_code == 401
        assert (await client.get("/api/accounts", headers=_bearer(rotated["token"]))).status_code == 200

    async def test_only_an_active_token_can_be_rotated(self, client: AsyncClient, auth_headers: dict):
        created = await _make(client, auth_headers)
        await client.delete(f"/api/api-tokens/{created['item']['id']}", headers=auth_headers)
        assert (await client.post(f"/api/api-tokens/{created['item']['id']}/rotate", headers=auth_headers)).status_code == 409

    async def test_a_token_of_another_workspace_is_not_reachable(
        self, client: AsyncClient, session: AsyncSession, test_user: User, auth_headers: dict
    ):
        other = Workspace(id=uuid.uuid4(), name="Outro", kind="business", created_by_user_id=test_user.id)
        session.add(other)
        await session.flush()
        foreign = ApiToken(
            workspace_id=other.id, user_id=test_user.id, name="Alheio", prefix="sfn_00000000",
            token_hash="0" * 64, scopes=["export.read"], expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
        session.add(foreign)
        await session.commit()

        assert (await client.delete(f"/api/api-tokens/{foreign.id}", headers=auth_headers)).status_code == 404
        assert (await client.post(f"/api/api-tokens/{foreign.id}/rotate", headers=auth_headers)).status_code == 404
        assert (await client.get("/api/api-tokens", headers=auth_headers)).json() == []
