"""API integration tests for webhook endpoints (F2).

Covers:
  - List endpoints (member access)
  - Create / update / delete (owner gated by webhooks.manage)
  - List deliveries
  - Redeliver
  - 403 when editor tries to create
  - 422 for unknown event type
"""
from __future__ import annotations

import uuid

import pytest
import respx
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _ws_url(ws_id, *parts) -> str:
    path = "/".join(str(p) for p in parts)
    return f"/api/workspaces/{ws_id}/webhooks/{path}".rstrip("/")


# ---------------------------------------------------------------------------
# List (any member may read)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_endpoints_empty(client: AsyncClient, auth_headers: dict, test_workspace):
    r = await client.get(_ws_url(test_workspace.id), headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_endpoint(client: AsyncClient, auth_headers: dict, test_workspace):
    r = await client.post(
        _ws_url(test_workspace.id),
        json={"url": "https://hook.example.com/rx", "events": ["transaction.created"]},
        headers=auth_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["url"] == "https://hook.example.com/rx"
    assert data["events"] == ["transaction.created"]
    assert data["is_active"] is True
    assert "secret" not in data


@pytest.mark.asyncio
async def test_create_endpoint_unknown_event_returns_422(
    client: AsyncClient, auth_headers: dict, test_workspace
):
    r = await client.post(
        _ws_url(test_workspace.id),
        json={"url": "https://hook.example.com/rx", "events": ["does.not.exist"]},
        headers=auth_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_endpoint_editor_forbidden(
    client: AsyncClient, session: AsyncSession, test_workspace, test_user: User
):
    """Editors (no webhooks.manage) get 403."""
    import bcrypt

    hashed = bcrypt.hashpw(b"pass", bcrypt.gensalt()).decode()
    editor = User(
        id=uuid.uuid4(),
        email="editor@example.com",
        hashed_password=hashed,
        is_active=True,
        is_verified=True,
        preferences={"language": "en", "date_format": "MM/DD/YYYY", "timezone": "UTC", "currency_display": "USD"},
    )
    session.add(editor)
    await session.flush()
    session.add(WorkspaceMember(
        id=uuid.uuid4(),
        workspace_id=test_workspace.id,
        user_id=editor.id,
        role="editor",
    ))
    await session.commit()

    r_login = await client.post(
        "/api/auth/login",
        data={"username": "editor@example.com", "password": "pass"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r_login.status_code == 200
    token = r_login.json()["access_token"]

    r = await client.post(
        _ws_url(test_workspace.id),
        json={"url": "https://hook.example.com/rx", "events": ["transaction.created"]},
        headers={"Authorization": f"Bearer {token}", "X-Workspace-Id": str(test_workspace.id)},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Update / Delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_endpoint(client: AsyncClient, auth_headers: dict, test_workspace):
    r_create = await client.post(
        _ws_url(test_workspace.id),
        json={"url": "https://hook.example.com/rx", "events": ["transaction.created"]},
        headers=auth_headers,
    )
    ep_id = r_create.json()["id"]

    r = await client.patch(
        _ws_url(test_workspace.id, ep_id),
        json={"is_active": False, "events": ["invoice.paid"]},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["is_active"] is False
    assert data["events"] == ["invoice.paid"]


@pytest.mark.asyncio
async def test_delete_endpoint(client: AsyncClient, auth_headers: dict, test_workspace):
    r_create = await client.post(
        _ws_url(test_workspace.id),
        json={"url": "https://hook.example.com/rx", "events": []},
        headers=auth_headers,
    )
    ep_id = r_create.json()["id"]

    r = await client.delete(_ws_url(test_workspace.id, ep_id), headers=auth_headers)
    assert r.status_code == 204

    r_list = await client.get(_ws_url(test_workspace.id), headers=auth_headers)
    assert r_list.json() == []


@pytest.mark.asyncio
async def test_update_nonexistent_endpoint_returns_404(
    client: AsyncClient, auth_headers: dict, test_workspace
):
    r = await client.patch(
        _ws_url(test_workspace.id, uuid.uuid4()),
        json={"is_active": False},
        headers=auth_headers,
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Deliveries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_list_deliveries_after_dispatch(
    client: AsyncClient, auth_headers: dict, test_workspace
):
    respx.post("https://hook.example.com/rx").mock(return_value=Response(200))

    r_create = await client.post(
        _ws_url(test_workspace.id),
        json={"url": "https://hook.example.com/rx", "events": ["transaction.created"]},
        headers=auth_headers,
    )
    ep_id = r_create.json()["id"]

    # Trigger a dispatch by creating a transaction via the API would require
    # account etc. — we directly call the service to keep the test focused.
    from app.core.database import async_session_maker  # type: ignore[attr-defined]
    from app.services import webhook_service

    async with async_session_maker() as svc_session:
        await webhook_service.dispatch_event(
            svc_session, test_workspace.id, "transaction.created", {"id": "t1"}
        )
        await svc_session.commit()

    r = await client.get(_ws_url(test_workspace.id, ep_id, "deliveries"), headers=auth_headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert items[0]["event_type"] == "transaction.created"


# ---------------------------------------------------------------------------
# Redeliver
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_redeliver_endpoint(
    client: AsyncClient, auth_headers: dict, test_workspace
):
    respx.post("https://hook.example.com/rx").mock(return_value=Response(500))

    r_create = await client.post(
        _ws_url(test_workspace.id),
        json={"url": "https://hook.example.com/rx", "events": ["transaction.created"]},
        headers=auth_headers,
    )
    ep_id = r_create.json()["id"]

    from app.core.database import async_session_maker  # type: ignore[attr-defined]
    from app.services import webhook_service

    async with async_session_maker() as svc_session:
        await webhook_service.dispatch_event(
            svc_session, test_workspace.id, "transaction.created", {}
        )
        await svc_session.commit()

    r_deliveries = await client.get(
        _ws_url(test_workspace.id, ep_id, "deliveries"), headers=auth_headers
    )
    delivery_id = r_deliveries.json()[0]["id"]

    # Now redeliver — success this time
    respx.post("https://hook.example.com/rx").mock(return_value=Response(200))
    r = await client.post(
        _ws_url(test_workspace.id, ep_id, "deliveries", delivery_id, "redeliver"),
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["http_status"] == 200
