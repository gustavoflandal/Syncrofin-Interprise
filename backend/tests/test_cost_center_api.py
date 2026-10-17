"""Tests for the CostCenter CRUD API (Task A3).

Fixtures are adapted from the project conftest: `client` + `auth_headers`
play the role of `owner_client`, and `client` + `viewer_auth_headers` play
`viewer_client`. The `test_user` and `test_workspace` fixtures supply the
user and workspace objects.
"""
import uuid
from decimal import Decimal
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace, WorkspaceMember
from app.models.user import User

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _owner_headers(auth_headers):
    """Forward the auth headers for the owner role."""
    return auth_headers


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

async def test_list_cost_centers_empty(client: AsyncClient, auth_headers, test_workspace: Workspace):
    resp = await client.get("/api/cost-centers", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def test_create_cost_center(client: AsyncClient, auth_headers, test_workspace: Workspace):
    resp = await client.post(
        "/api/cost-centers",
        json={"name": "Marketing", "code": "MKT", "description": "Dept de marketing"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Marketing"
    assert data["code"] == "MKT"
    assert data["is_active"] is True


async def test_create_requires_admin(
    client: AsyncClient, viewer_auth_headers, test_workspace: Workspace
):
    resp = await client.post(
        "/api/cost-centers",
        json={"name": "X"},
        headers=viewer_auth_headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

async def test_update_cost_center(client: AsyncClient, auth_headers, test_workspace: Workspace):
    cc = (
        await client.post("/api/cost-centers", json={"name": "CC"}, headers=auth_headers)
    ).json()
    resp = await client.patch(
        f"/api/cost-centers/{cc['id']}",
        json={"name": "CC Renamed"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "CC Renamed"


# ---------------------------------------------------------------------------
# Delete — unused → hard delete (204)
# ---------------------------------------------------------------------------

async def test_delete_unused_cost_center(
    client: AsyncClient, auth_headers, test_workspace: Workspace
):
    cc = (
        await client.post("/api/cost-centers", json={"name": "Temp"}, headers=auth_headers)
    ).json()
    resp = await client.delete(f"/api/cost-centers/{cc['id']}", headers=auth_headers)
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Delete — in-use → soft deactivate (200 with is_active=False)
# ---------------------------------------------------------------------------

async def test_delete_used_cost_center_deactivates(
    client: AsyncClient,
    auth_headers,
    test_workspace: Workspace,
    test_user: User,
    session: AsyncSession,
):
    from app.models.transaction import Transaction
    from app.models.account import Account

    cc = (
        await client.post("/api/cost-centers", json={"name": "Em uso"}, headers=auth_headers)
    ).json()

    # Create an account and a transaction that references the CC directly via the ORM.
    account = Account(
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        name="Test CC Account",
        currency="BRL",
        type="checking",
        balance=Decimal("0"),
    )
    session.add(account)
    await session.flush()

    tx = Transaction(
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        account_id=account.id,
        cost_center_id=uuid.UUID(cc["id"]),
        description="TX with CC",
        amount=Decimal("10"),
        date=date.today(),
        effective_date=date.today(),
        type="debit",
        source="manual",
    )
    session.add(tx)
    await session.commit()

    resp = await client.delete(f"/api/cost-centers/{cc['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


# ---------------------------------------------------------------------------
# Verify transaction endpoint accepts cost_center_id (no 422 for the field)
# ---------------------------------------------------------------------------

async def test_transaction_with_cost_center(
    client: AsyncClient, auth_headers, test_workspace: Workspace
):
    cc = (
        await client.post("/api/cost-centers", json={"name": "Ops"}, headers=auth_headers)
    ).json()
    cc_id = cc["id"]

    # Create a manual account so we have a valid account_id for the transaction.
    account = (
        await client.post(
            "/api/accounts",
            json={"name": "Caixa", "type": "checking", "balance": "0.00", "currency": "BRL"},
            headers=auth_headers,
        )
    ).json()
    account_id = account["id"]

    resp = await client.post(
        "/api/transactions",
        json={
            "cost_center_id": cc_id,
            "account_id": account_id,
            "description": "TX com CC",
            "amount": "10.00",
            "date": "2026-01-01",
            "type": "debit",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["cost_center_id"] == cc_id


# ---------------------------------------------------------------------------
# Wrong workspace → 404
# ---------------------------------------------------------------------------

async def test_cost_center_wrong_workspace(
    client: AsyncClient, auth_headers, test_workspace: Workspace
):
    fake_id = str(uuid.uuid4())
    resp = await client.patch(
        f"/api/cost-centers/{fake_id}",
        json={"name": "X"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Workspace isolation: attaching a foreign cost center must be rejected
# ---------------------------------------------------------------------------

async def test_transaction_rejects_foreign_cost_center(
    client: AsyncClient,
    auth_headers,
    test_workspace: Workspace,
    test_user: User,
    session: AsyncSession,
):
    """A cost center that belongs to workspace B must not be attachable to a
    transaction in workspace A — cross-tenant data leakage guard."""
    from app.models.account import Account
    from app.models.cost_center import CostCenter

    # Create a second workspace that the same user also owns.
    ws_b = Workspace(
        id=uuid.uuid4(),
        name="Workspace B",
        kind="personal",
        created_by_user_id=test_user.id,
        default_currency="BRL",
    )
    session.add(ws_b)
    await session.flush()
    session.add(
        WorkspaceMember(
            id=uuid.uuid4(),
            workspace_id=ws_b.id,
            user_id=test_user.id,
            role="owner",
        )
    )
    await session.flush()

    # Create a cost center that belongs to workspace B.
    cc_b = CostCenter(
        id=uuid.uuid4(),
        workspace_id=ws_b.id,
        name="CC from workspace B",
    )
    session.add(cc_b)

    # Create an account in the user's primary workspace (workspace A).
    account = Account(
        user_id=test_user.id,
        workspace_id=test_workspace.id,
        name="Account WS-A",
        currency="BRL",
        type="checking",
        balance=Decimal("0"),
    )
    session.add(account)
    await session.flush()
    await session.commit()

    # Attempt to create a transaction in workspace A with the CC from workspace B.
    resp = await client.post(
        "/api/transactions",
        json={
            "account_id": str(account.id),
            "cost_center_id": str(cc_b.id),
            "description": "Cross-tenant TX",
            "amount": "50.00",
            "date": "2026-01-01",
            "type": "debit",
        },
        headers=auth_headers,
    )
    # The service raises HTTPException(status_code=404, detail="cost_center_not_found")
    # for a cost center not in the workspace.
    assert resp.status_code == 404
    assert "cost_center" in resp.text
