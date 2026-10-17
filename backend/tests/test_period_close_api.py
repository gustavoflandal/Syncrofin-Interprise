"""API tests for period-close endpoints.

Covers:
  - Listing closes (empty workspace)
  - Closing a period (201)
  - Reopening a period (DELETE, 200)
  - Permission enforcement: editor may not close a period (403)
"""
import json
import uuid

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember


@pytest.mark.asyncio
async def test_list_period_closes_empty(
    client: AsyncClient, auth_headers: dict, test_workspace
):
    r = await client.get(
        f"/api/workspaces/{test_workspace.id}/period-closes",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_close_period(
    client: AsyncClient, auth_headers: dict, test_workspace
):
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/period-closes",
        json={"year": 2026, "month": 1, "reason": "Fechado"},
        headers=auth_headers,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["year"] == 2026
    assert data["month"] == 1
    assert data["reopened_at"] is None
    assert data["is_open"] is False


@pytest.mark.asyncio
async def test_close_period_duplicate_returns_409(
    client: AsyncClient, auth_headers: dict, test_workspace
):
    await client.post(
        f"/api/workspaces/{test_workspace.id}/period-closes",
        json={"year": 2026, "month": 2},
        headers=auth_headers,
    )
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/period-closes",
        json={"year": 2026, "month": 2},
        headers=auth_headers,
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_reopen_period(
    client: AsyncClient, auth_headers: dict, test_workspace
):
    await client.post(
        f"/api/workspaces/{test_workspace.id}/period-closes",
        json={"year": 2026, "month": 1},
        headers=auth_headers,
    )
    r = await client.request(
        "DELETE",
        f"/api/workspaces/{test_workspace.id}/period-closes/2026/1",
        content=json.dumps({"reason": "Precisa de correção"}),
        headers={**auth_headers, "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["reopened_at"] is not None
    assert data["is_open"] is True


@pytest.mark.asyncio
async def test_reopen_nonexistent_period_returns_404(
    client: AsyncClient, auth_headers: dict, test_workspace
):
    r = await client.request(
        "DELETE",
        f"/api/workspaces/{test_workspace.id}/period-closes/2024/6",
        content=json.dumps({}),
        headers={**auth_headers, "Content-Type": "application/json"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_shows_closed_period(
    client: AsyncClient, auth_headers: dict, test_workspace
):
    await client.post(
        f"/api/workspaces/{test_workspace.id}/period-closes",
        json={"year": 2025, "month": 3},
        headers=auth_headers,
    )
    r = await client.get(
        f"/api/workspaces/{test_workspace.id}/period-closes",
        headers=auth_headers,
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1
    assert any(i["year"] == 2025 and i["month"] == 3 for i in items)


@pytest.mark.asyncio
async def test_close_uses_header_workspace_not_path_workspace(
    client: AsyncClient,
    auth_headers: dict,
    test_workspace,
    session: AsyncSession,
):
    """Verifica que ctx.workspace.id (do header) é usado, não o path param.

    Um usuário autenticado no workspace A (via X-Workspace-Id: <A>) que envia
    uma request para /api/workspaces/<B>/period-closes deve ter o fechamento
    gravado no workspace A, porque ctx.workspace.id vem do header, não do path.
    """
    # Cria um segundo workspace distinto e adiciona o test_user como owner
    # para que a listagem no final possa ser verificada via X-Workspace-Id.
    other_ws = Workspace(
        id=uuid.uuid4(),
        name="Other WS",
        kind="personal",
        created_by_user_id=test_workspace.created_by_user_id,
        default_currency="BRL",
    )
    session.add(other_ws)
    await session.flush()
    session.add(
        WorkspaceMember(
            id=uuid.uuid4(),
            workspace_id=other_ws.id,
            user_id=test_workspace.created_by_user_id,
            role="owner",
        )
    )
    await session.commit()

    # Faz POST com path de other_ws mas header X-Workspace-Id do test_workspace.
    # O header vence: ctx.workspace.id == test_workspace.id.
    r = await client.post(
        f"/api/workspaces/{other_ws.id}/period-closes",
        json={"year": 2026, "month": 6},
        headers={**auth_headers, "X-Workspace-Id": str(test_workspace.id)},
    )
    assert r.status_code == 201

    # O fechamento deve estar em test_workspace (do header), NÃO em other_ws (do path).
    list_own = await client.get(
        f"/api/workspaces/{test_workspace.id}/period-closes",
        headers={**auth_headers, "X-Workspace-Id": str(test_workspace.id)},
    )
    list_other = await client.get(
        f"/api/workspaces/{other_ws.id}/period-closes",
        headers={**auth_headers, "X-Workspace-Id": str(other_ws.id)},
    )
    assert list_own.status_code == 200
    assert list_other.status_code == 200
    assert any(p["year"] == 2026 and p["month"] == 6 for p in list_own.json())
    assert not any(p["year"] == 2026 and p["month"] == 6 for p in list_other.json())


@pytest.mark.asyncio
async def test_close_period_requires_periods_manage(
    client: AsyncClient,
    test_workspace,
    session: AsyncSession,
):
    """An editor may not close a period — periods.manage is admin-only."""
    hashed = bcrypt.hashpw(b"pass123", bcrypt.gensalt()).decode()
    editor = User(
        id=uuid.uuid4(),
        email="editor_pc@x.com",
        hashed_password=hashed,
        is_active=True,
        is_verified=True,
    )
    session.add(editor)
    session.add(
        WorkspaceMember(
            workspace_id=test_workspace.id,
            user_id=editor.id,
            role="editor",
        )
    )
    await session.commit()

    from tests.conftest import issue_test_token

    token = await issue_test_token(editor)
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/period-closes",
        json={"year": 2026, "month": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
