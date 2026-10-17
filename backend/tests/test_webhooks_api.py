"""Webhooks de saída por workspace — testes de API (F2).

Cobre: autenticação, CRUD básico, gate de permissão (workspace.manage vs
export.read), endpoint de teste e validação de event_types.
"""
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wh_payload(**kwargs) -> dict:
    return {"url": "https://example.com/hook", **kwargs}


async def _create(client: AsyncClient, headers: dict, **kwargs) -> dict:
    resp = await client.post("/api/webhooks", json=_wh_payload(**kwargs), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _viewer(session: AsyncSession, workspace: Workspace) -> tuple[User, dict]:
    """Member with 'viewer' role (has export.read, lacks workspace.manage)."""
    from tests.conftest import issue_test_token

    user = User(
        id=uuid.uuid4(),
        email=f"viewer-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=workspace.id, user_id=user.id, role="viewer"))
    await session.commit()
    tok = await issue_test_token(user)
    return user, {"Authorization": f"Bearer {tok}", "X-Workspace-Id": str(workspace.id)}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWebhookCrud:
    async def test_unauthenticated_list_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/webhooks")
        assert resp.status_code == 401

    async def test_create_and_list(self, client: AsyncClient, auth_headers: dict):
        wh = await _create(client, auth_headers)
        assert wh["url"] == "https://example.com/hook"
        assert wh["active"] is True
        assert wh["has_secret"] is False
        assert wh["event_types"] is None  # all events

        listed = (await client.get("/api/webhooks", headers=auth_headers)).json()
        assert any(w["id"] == wh["id"] for w in listed)

    async def test_create_with_secret_does_not_leak(self, client: AsyncClient, auth_headers: dict):
        wh = await _create(client, auth_headers, secret="supersecret")
        assert wh["has_secret"] is True
        assert "supersecret" not in str(wh)

    async def test_create_with_event_types(self, client: AsyncClient, auth_headers: dict):
        wh = await _create(client, auth_headers, event_types=["transaction.created", "invoice.paid"])
        assert set(wh["event_types"]) == {"transaction.created", "invoice.paid"}

    async def test_create_invalid_event_type_returns_422(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/webhooks",
            json=_wh_payload(event_types=["nonexistent.event"]),
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_get_one(self, client: AsyncClient, auth_headers: dict):
        wh = await _create(client, auth_headers)
        resp = await client.get(f"/api/webhooks/{wh['id']}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == wh["id"]

    async def test_get_missing_returns_404(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get(f"/api/webhooks/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_update_deactivates(self, client: AsyncClient, auth_headers: dict):
        wh = await _create(client, auth_headers)
        resp = await client.put(f"/api/webhooks/{wh['id']}", json={"active": False}, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["active"] is False

    async def test_delete(self, client: AsyncClient, auth_headers: dict):
        wh = await _create(client, auth_headers)
        del_resp = await client.delete(f"/api/webhooks/{wh['id']}", headers=auth_headers)
        assert del_resp.status_code == 204
        get_resp = await client.get(f"/api/webhooks/{wh['id']}", headers=auth_headers)
        assert get_resp.status_code == 404

    async def test_list_event_types(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/webhooks/event-types", headers=auth_headers)
        assert resp.status_code == 200
        types = resp.json()
        assert "transaction.created" in types
        assert "invoice.paid" in types


class TestWebhookPermissions:
    async def test_viewer_can_list_but_not_create(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, auth_headers: dict
    ):
        # owner creates first
        wh = await _create(client, auth_headers)
        _, viewer_headers = await _viewer(session, test_workspace)

        list_resp = await client.get("/api/webhooks", headers=viewer_headers)
        assert list_resp.status_code == 200
        assert any(w["id"] == wh["id"] for w in list_resp.json())

        create_resp = await client.post("/api/webhooks", json=_wh_payload(), headers=viewer_headers)
        assert create_resp.status_code == 403

    async def test_viewer_cannot_delete(
        self, client: AsyncClient, session: AsyncSession, test_workspace: Workspace, auth_headers: dict
    ):
        wh = await _create(client, auth_headers)
        _, viewer_headers = await _viewer(session, test_workspace)
        resp = await client.delete(f"/api/webhooks/{wh['id']}", headers=viewer_headers)
        assert resp.status_code == 403


class TestWebhookTest:
    async def test_test_endpoint_returns_scheduled(self, client: AsyncClient, auth_headers: dict):
        wh = await _create(client, auth_headers)
        resp = await client.post(f"/api/webhooks/{wh['id']}/test", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["scheduled"] is True

    async def test_test_endpoint_missing_returns_404(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(f"/api/webhooks/{uuid.uuid4()}/test", headers=auth_headers)
        assert resp.status_code == 404
