"""The D1 routes: a person's own access/portability/correction/erasure, and the admin's queue."""
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

pytestmark = pytest.mark.asyncio

BASE = "/api/data-requests"
ADMIN = "/api/admin/data-requests"


@pytest_asyncio.fixture
async def api_token_headers(client: AsyncClient, auth_headers: dict) -> dict:
    """An API-token bearer header, made exactly as `tests/test_api_tokens.py` does it: no shared
    `api_token_headers` fixture exists yet, so this is a local copy of that pattern."""
    created = await client.post(
        "/api/api-tokens", json={"name": "Integração", "scopes": ["export.read"], "days": 30}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    secret = created.json()["token"]
    return {"Authorization": f"Bearer {secret}"}


class TestOwnRequests:
    async def test_access_returns_a_zip_and_lists_afterwards(
        self, client: AsyncClient, auth_headers: dict, test_workspace: Workspace
    ):
        response = await client.post(BASE, json={"kind": "access"}, headers=auth_headers)
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "application/zip"

        listed = await client.get(BASE, headers=auth_headers)
        assert listed.status_code == 200
        assert listed.json()["items"][0]["kind"] == "access"

    async def test_correction_self_service_resolves_immediately(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(
            BASE, json={"kind": "correction", "self_service": True}, headers=auth_headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "resolved_auto"

    async def test_correction_self_service_includes_the_self_service_links(
        self, client: AsyncClient, auth_headers: dict
    ):
        from app.services.data_subject_request_service import SELF_SERVICE_LINKS

        response = await client.post(
            BASE, json={"kind": "correction", "self_service": True}, headers=auth_headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["self_service_links"] == SELF_SERVICE_LINKS

    async def test_correction_without_self_service_needs_detail(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(
            BASE, json={"kind": "correction", "self_service": False}, headers=auth_headers
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "DETAIL_REQUIRED"

    async def test_non_self_service_correction_has_no_self_service_links(
        self, client: AsyncClient, auth_headers: dict
    ):
        response = await client.post(
            BASE, json={"kind": "correction", "self_service": False, "detail": "endereço errado"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["self_service_links"] is None

    async def test_access_request_has_no_self_service_links(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(BASE, json={"kind": "access"}, headers=auth_headers)
        assert response.status_code == 200
        listed = await client.get(BASE, headers=auth_headers)
        assert listed.json()["items"][0]["self_service_links"] is None

    async def test_an_unauthenticated_request_is_refused(self, client: AsyncClient):
        response = await client.post(BASE, json={"kind": "access"})
        assert response.status_code == 401

    async def test_an_api_token_is_refused(self, client: AsyncClient, api_token_headers: dict):
        response = await client.post(BASE, json={"kind": "access"}, headers=api_token_headers)
        assert response.status_code == 403


class TestErasure:
    async def test_wrong_password_is_refused(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(f"{BASE}/erasure", json={"password": "wrong"}, headers=auth_headers)
        assert response.status_code == 401

    async def test_correct_password_deletes_the_account(self, client: AsyncClient, auth_headers: dict):
        response = await client.post(f"{BASE}/erasure", json={"password": "testpass123"}, headers=auth_headers)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "resolved_auto"
        again = await client.get(BASE, headers=auth_headers)
        assert again.status_code == 401  # the session's user no longer exists

    async def test_sole_ownership_of_a_shared_workspace_blocks_it_with_409(
        self, client: AsyncClient, auth_headers: dict, session: AsyncSession, test_user: User, test_workspace: Workspace
    ):
        other = User(
            id=uuid.uuid4(), email="other-erasure@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add(other)
        await session.flush()
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=other.id, role="editor"))
        await session.commit()

        response = await client.post(f"{BASE}/erasure", json={"password": "testpass123"}, headers=auth_headers)
        assert response.status_code == 409
        body = response.json()["detail"]
        assert body["code"] == "WORKSPACES_BLOCK_ERASURE"
        assert test_workspace.name in body["workspaces"]
        assert body["protocol"].startswith("DSR-")

        still_there = await client.get(BASE, headers=auth_headers)
        assert still_there.status_code == 200

    async def test_editor_with_own_data_in_someone_elses_shared_workspace_blocks_it_with_409(
        self, client: AsyncClient, auth_headers: dict, session: AsyncSession, test_user: User
    ):
        """test_user is merely an `editor` (not role='owner') of a workspace owned by someone else and
        shared with a third member, but has their own data row in it — the new coverage from Fix 1."""
        from app.models.account import Account

        owner = User(
            id=uuid.uuid4(), email="owner-erasure-api@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        third = User(
            id=uuid.uuid4(), email="third-erasure-api@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add_all([owner, third])
        await session.flush()

        shared = Workspace(
            id=uuid.uuid4(), name="Workspace Compartilhado API", kind="personal",
            created_by_user_id=owner.id, default_currency="BRL",
        )
        session.add(shared)
        await session.flush()
        session.add_all([
            WorkspaceMember(id=uuid.uuid4(), workspace_id=shared.id, user_id=owner.id, role="owner"),
            WorkspaceMember(id=uuid.uuid4(), workspace_id=shared.id, user_id=test_user.id, role="editor"),
            WorkspaceMember(id=uuid.uuid4(), workspace_id=shared.id, user_id=third.id, role="viewer"),
        ])
        session.add(Account(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=shared.id,
            name="Conta do editor", type="checking", currency="BRL",
        ))
        await session.commit()

        response = await client.post(f"{BASE}/erasure", json={"password": "testpass123"}, headers=auth_headers)
        assert response.status_code == 409
        body = response.json()["detail"]
        assert body["code"] == "WORKSPACES_BLOCK_ERASURE"
        assert shared.name in body["workspaces"]

        still_there = await client.get(BASE, headers=auth_headers)
        assert still_there.status_code == 200


class TestAdminQueue:
    async def test_a_regular_user_is_refused(self, client: AsyncClient, auth_headers: dict):
        response = await client.get(ADMIN, headers=auth_headers)
        assert response.status_code == 403

    async def test_the_admin_sees_pending_requests_and_can_resolve_them(
        self, client: AsyncClient, auth_headers: dict, admin_auth_headers: dict
    ):
        created = await client.post(
            BASE, json={"kind": "correction", "self_service": False, "detail": "endereço errado"},
            headers=auth_headers,
        )
        request_id = created.json()["id"]

        queue = await client.get(ADMIN, params={"status": "pending"}, headers=admin_auth_headers)
        assert queue.status_code == 200
        assert any(item["id"] == request_id for item in queue.json()["items"])

        resolved = await client.patch(
            f"{ADMIN}/{request_id}", json={"status": "resolved_manual", "resolution_note": "corrigido"},
            headers=admin_auth_headers,
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "resolved_manual"

    async def test_resolving_an_already_resolved_request_is_refused(
        self, client: AsyncClient, auth_headers: dict, admin_auth_headers: dict
    ):
        await client.post(BASE, json={"kind": "access"}, headers=auth_headers)
        # `access` resolves immediately — re-parse from the follow-up list call to get its id
        listed = await client.get(BASE, headers=auth_headers)
        request_id = listed.json()["items"][0]["id"]

        response = await client.patch(
            f"{ADMIN}/{request_id}", json={"status": "resolved_manual"}, headers=admin_auth_headers
        )
        assert response.status_code == 409

    async def test_the_admin_sees_who_filed_each_request(
        self, client: AsyncClient, auth_headers: dict, admin_auth_headers: dict, test_user: User
    ):
        """D1 Fix 5: the admin queue names the requester (id + e-mail); the person's own view doesn't."""
        created = await client.post(
            BASE, json={"kind": "correction", "self_service": False, "detail": "endereço errado"},
            headers=auth_headers,
        )
        request_id = created.json()["id"]
        assert "user_id" not in created.json()
        assert "actor_email" not in created.json()

        queue = await client.get(ADMIN, params={"status": "pending"}, headers=admin_auth_headers)
        assert queue.status_code == 200
        item = next(item for item in queue.json()["items"] if item["id"] == request_id)
        assert item["user_id"] == str(test_user.id)
        assert item["actor_email"] == test_user.email

        resolved = await client.patch(
            f"{ADMIN}/{request_id}", json={"status": "resolved_manual", "resolution_note": "corrigido"},
            headers=admin_auth_headers,
        )
        assert resolved.status_code == 200
        assert resolved.json()["user_id"] == str(test_user.id)
        assert resolved.json()["actor_email"] == test_user.email

        own_view = await client.get(BASE, headers=auth_headers)
        own_item = next(item for item in own_view.json()["items"] if item["id"] == request_id)
        assert "user_id" not in own_item
        assert "actor_email" not in own_item

    async def test_a_request_from_a_since_erased_user_shows_no_email_not_a_500(
        self, client: AsyncClient, admin_auth_headers: dict, session: AsyncSession
    ):
        """`DataSubjectRequest.user_id` cascades away with the user on purpose (see the model's
        docstring), so a request row never actually outlives its user in this schema — but the admin
        route's LEFT JOIN must still degrade gracefully if it ever did (e.g. a future FK change). Triggers
        are disabled here only to manufacture that otherwise-unreachable state for the test."""
        import uuid as _uuid

        from app.models.data_subject_request import DataSubjectRequest, generate_protocol

        ghost_user_id = _uuid.uuid4()
        request_id = _uuid.uuid4()
        await session.execute(text("ALTER TABLE data_subject_requests DISABLE TRIGGER ALL"))
        try:
            session.add(DataSubjectRequest(
                id=request_id,
                protocol=generate_protocol(),
                user_id=ghost_user_id,
                kind="correction",
                status="pending",
                detail="conta já não existe",
            ))
            await session.flush()
        finally:
            await session.execute(text("ALTER TABLE data_subject_requests ENABLE TRIGGER ALL"))
        await session.commit()

        queue = await client.get(ADMIN, params={"status": "pending"}, headers=admin_auth_headers)
        assert queue.status_code == 200
        item = next(item for item in queue.json()["items"] if item["id"] == str(request_id))
        assert item["user_id"] == str(ghost_user_id)
        assert item["actor_email"] is None
