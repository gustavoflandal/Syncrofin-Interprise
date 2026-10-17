"""API tests for the approvals endpoints.

Covers:
  - Listing pending transactions (empty)
  - Threshold check with no rules (needs_approval=False)
  - Creating a rule and verifying threshold flips to needs_approval=True
  - Permission enforcement: editor → 403 on approve
"""
from __future__ import annotations

import uuid

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember


@pytest.mark.asyncio
async def test_pending_empty(
    client: AsyncClient, auth_headers: dict, test_workspace: Workspace
):
    """An empty workspace has no pending approvals."""
    r = await client.get(
        f"/api/workspaces/{test_workspace.id}/approvals/pending",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_threshold_no_rule_returns_false(
    client: AsyncClient, auth_headers: dict, test_workspace: Workspace
):
    """Without any approval rule, needs_approval is always False."""
    r = await client.get(
        f"/api/workspaces/{test_workspace.id}/approvals/threshold?amount=9999",
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["needs_approval"] is False
    assert body["threshold"] is None


@pytest.mark.asyncio
async def test_create_rule_and_threshold(
    client: AsyncClient, auth_headers: dict, test_workspace: Workspace
):
    """After creating a rule, amounts above the threshold require approval."""
    # Create a global rule with a 1000 BRL threshold
    cr = await client.post(
        f"/api/workspaces/{test_workspace.id}/approval-rules",
        json={"amount_threshold": "1000.00", "currency": "BRL"},
        headers=auth_headers,
    )
    assert cr.status_code == 201
    rule = cr.json()
    assert rule["amount_threshold"] == "1000.00"
    assert rule["currency"] == "BRL"

    # Amount above the threshold should require approval
    r = await client.get(
        f"/api/workspaces/{test_workspace.id}/approvals/threshold?amount=1500",
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["needs_approval"] is True

    # Amount at or below the threshold does not require approval
    r2 = await client.get(
        f"/api/workspaces/{test_workspace.id}/approvals/threshold?amount=999",
        headers=auth_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["needs_approval"] is False


@pytest.mark.asyncio
async def test_list_rules(
    client: AsyncClient, auth_headers: dict, test_workspace: Workspace
):
    """GET approval-rules returns the rules just created."""
    from decimal import Decimal as _Decimal

    await client.post(
        f"/api/workspaces/{test_workspace.id}/approval-rules",
        json={"amount_threshold": "500.00", "currency": "BRL"},
        headers=auth_headers,
    )
    r = await client.get(
        f"/api/workspaces/{test_workspace.id}/approval-rules",
        headers=auth_headers,
    )
    assert r.status_code == 200
    items = r.json()
    # Compare as Decimal to be robust against DB-round-trip precision ("500.00" vs "500.0000")
    assert any(_Decimal(item["amount_threshold"]) == _Decimal("500.00") for item in items)


@pytest.mark.asyncio
async def test_delete_rule(
    client: AsyncClient, auth_headers: dict, test_workspace: Workspace
):
    """DELETE a rule removes it from the list."""
    cr = await client.post(
        f"/api/workspaces/{test_workspace.id}/approval-rules",
        json={"amount_threshold": "750.00", "currency": "BRL"},
        headers=auth_headers,
    )
    assert cr.status_code == 201
    rule_id = cr.json()["id"]

    dr = await client.delete(
        f"/api/workspaces/{test_workspace.id}/approval-rules/{rule_id}",
        headers=auth_headers,
    )
    assert dr.status_code == 204

    r = await client.get(
        f"/api/workspaces/{test_workspace.id}/approval-rules",
        headers=auth_headers,
    )
    assert not any(item["id"] == rule_id for item in r.json())


@pytest.mark.asyncio
async def test_approve_requires_approvals_approve(
    client: AsyncClient,
    test_workspace: Workspace,
    session: AsyncSession,
):
    """A viewer (without approvals.approve) receives 403 on the approve endpoint.

    Editors have the approvals.approve permission (it is in the "data" group that
    the editor role holds in full). Viewers only have export.read, so they are
    the correct boundary to assert the gate with.
    """
    hashed = bcrypt.hashpw(b"pass123", bcrypt.gensalt()).decode()
    viewer = User(
        id=uuid.uuid4(),
        email="viewer_ap@x.com",
        hashed_password=hashed,
        is_active=True,
        is_verified=True,
    )
    session.add(viewer)
    session.add(
        WorkspaceMember(
            workspace_id=test_workspace.id,
            user_id=viewer.id,
            role="viewer",
        )
    )
    await session.commit()

    from tests.conftest import issue_test_token

    token = await issue_test_token(viewer)
    r = await client.post(
        f"/api/workspaces/{test_workspace.id}/approvals/{uuid.uuid4()}/approve",
        json={},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Workspace-Id": str(test_workspace.id),
        },
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_rule_requires_workspace_manage(
    client: AsyncClient,
    test_workspace: Workspace,
    session: AsyncSession,
):
    """An editor cannot create approval rules (workspace.manage required)."""
    hashed = bcrypt.hashpw(b"pass456", bcrypt.gensalt()).decode()
    editor = User(
        id=uuid.uuid4(),
        email="editor_rule@x.com",
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
        f"/api/workspaces/{test_workspace.id}/approval-rules",
        json={"amount_threshold": "100.00", "currency": "BRL"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
