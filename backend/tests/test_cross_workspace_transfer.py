"""Tests for A9 cross-workspace (PF/PJ) transfers."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.bank_connection import BankConnection
from app.models.transaction import Transaction
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember


@pytest_asyncio.fixture
async def second_workspace(session: AsyncSession, test_user: User) -> Workspace:
    """A second workspace (business) owned by the same test user."""
    ws = Workspace(
        id=uuid.uuid4(),
        name="Empresa Teste",
        kind="business",
        default_currency="BRL",
    )
    session.add(ws)
    await session.flush()
    member = WorkspaceMember(
        workspace_id=ws.id,
        user_id=test_user.id,
        role="owner",
    )
    session.add(member)
    await session.commit()
    await session.refresh(ws)
    return ws


@pytest_asyncio.fixture
async def second_workspace_account(
    session: AsyncSession, test_user: User, second_workspace: Workspace
) -> Account:
    """A BRL account in the second (business) workspace."""
    conn = BankConnection(
        id=uuid.uuid4(),
        workspace_id=second_workspace.id,
        user_id=test_user.id,
        provider="manual",
        external_id=f"manual-{uuid.uuid4()}",
        institution_name="Manual",
        status="active",
    )
    session.add(conn)
    await session.flush()
    account = Account(
        id=uuid.uuid4(),
        user_id=test_user.id,
        connection_id=conn.id,
        external_id=f"acc-pj-{uuid.uuid4()}",
        name="Conta PJ",
        type="checking",
        balance=Decimal("0.00"),
        currency="BRL",
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    return account


@pytest.mark.asyncio
async def test_create_cross_workspace_transfer(
    client: AsyncClient,
    auth_headers: dict,
    test_account: Account,
    second_workspace: Workspace,
    second_workspace_account: Account,
):
    """Happy path: transfer from PF workspace to PJ workspace."""
    response = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": str(test_account.id),
            "to_account_id": str(second_workspace_account.id),
            "to_workspace_id": str(second_workspace.id),
            "amount": "1000.00",
            "date": date.today().isoformat(),
            "description": "Aporte de capital PF→PJ",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    data = response.json()

    assert data["debit"]["is_cross_workspace_transfer"] is True
    assert data["credit"]["is_cross_workspace_transfer"] is True
    assert data["debit"]["transfer_pair_id"] == data["credit"]["transfer_pair_id"]
    assert float(data["debit"]["amount"]) == 1000.00
    assert float(data["credit"]["amount"]) == 1000.00


@pytest.mark.asyncio
async def test_cross_workspace_transfer_different_workspaces(
    client: AsyncClient,
    auth_headers: dict,
    test_account: Account,
    second_workspace: Workspace,
    second_workspace_account: Account,
    session: AsyncSession,
):
    """Both legs must live in their respective workspaces."""
    response = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": str(test_account.id),
            "to_account_id": str(second_workspace_account.id),
            "to_workspace_id": str(second_workspace.id),
            "amount": "500.00",
            "date": date.today().isoformat(),
            "description": "Pró-labore",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    pair_id = uuid.UUID(response.json()["debit"]["transfer_pair_id"])

    result = await session.execute(
        select(Transaction).where(Transaction.transfer_pair_id == pair_id)
    )
    legs = result.scalars().all()
    assert len(legs) == 2
    workspace_ids = {leg.workspace_id for leg in legs}
    assert test_account.connection is not None or True  # just check two different ws
    # The two legs must live in different workspaces
    assert len(workspace_ids) == 2


@pytest.mark.asyncio
async def test_get_transfer_pair_cross_workspace(
    client: AsyncClient,
    auth_headers: dict,
    test_account: Account,
    second_workspace: Workspace,
    second_workspace_account: Account,
):
    """get_transfer_pair must return the counterpart even across workspaces."""
    create_resp = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": str(test_account.id),
            "to_account_id": str(second_workspace_account.id),
            "to_workspace_id": str(second_workspace.id),
            "amount": "250.00",
            "date": date.today().isoformat(),
            "description": "Empréstimo sócio-empresa",
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    debit_id = create_resp.json()["debit"]["id"]

    pair_resp = await client.get(
        f"/api/transactions/{debit_id}/transfer-pair",
        headers=auth_headers,
    )
    assert pair_resp.status_code == 200
    pair = pair_resp.json()
    assert pair is not None
    assert pair["is_cross_workspace_transfer"] is True
    assert pair["cross_workspace_partner_name"] == "Empresa Teste"


@pytest.mark.asyncio
async def test_cross_workspace_transfer_rejects_no_destination_access(
    client: AsyncClient,
    auth_headers: dict,
    test_account: Account,
    session: AsyncSession,
    test_user: User,
):
    """Must reject when the user is not a member of the destination workspace."""
    other_ws = Workspace(
        id=uuid.uuid4(),
        name="Workspace de Outro",
        kind="business",
        default_currency="BRL",
    )
    session.add(other_ws)
    await session.flush()
    other_conn = BankConnection(
        id=uuid.uuid4(),
        workspace_id=other_ws.id,
        user_id=test_user.id,
        provider="manual",
        external_id=f"manual-{uuid.uuid4()}",
        institution_name="Manual",
        status="active",
    )
    session.add(other_conn)
    await session.flush()
    other_account = Account(
        id=uuid.uuid4(),
        user_id=test_user.id,
        connection_id=other_conn.id,
        external_id=f"acc-other-{uuid.uuid4()}",
        name="Conta Alheia",
        type="checking",
        balance=Decimal("0.00"),
        currency="BRL",
    )
    session.add(other_account)
    await session.commit()

    response = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": str(test_account.id),
            "to_account_id": str(other_account.id),
            "to_workspace_id": str(other_ws.id),
            "amount": "100.00",
            "date": date.today().isoformat(),
            "description": "Tentativa indevida",
        },
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_cross_workspace_transfer_rejects_wrong_source_account(
    client: AsyncClient,
    auth_headers: dict,
    test_account: Account,
    second_workspace: Workspace,
    second_workspace_account: Account,
):
    """Source account must belong to the source workspace."""
    response = await client.post(
        "/api/transactions/transfer",
        json={
            # swap: use destination account as source — wrong workspace
            "from_account_id": str(second_workspace_account.id),
            "to_account_id": str(test_account.id),
            "to_workspace_id": str(second_workspace.id),
            "amount": "100.00",
            "date": date.today().isoformat(),
            "description": "Conta errada",
        },
        headers=auth_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_delete_cross_workspace_transfer_removes_both_legs(
    client: AsyncClient,
    auth_headers: dict,
    test_account: Account,
    second_workspace: Workspace,
    second_workspace_account: Account,
    session: AsyncSession,
):
    """Deleting one leg of a cross-workspace transfer removes both."""
    create_resp = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": str(test_account.id),
            "to_account_id": str(second_workspace_account.id),
            "to_workspace_id": str(second_workspace.id),
            "amount": "300.00",
            "date": date.today().isoformat(),
            "description": "Retirada pró-labore",
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    debit_id = create_resp.json()["debit"]["id"]
    credit_id = create_resp.json()["credit"]["id"]
    pair_id = uuid.UUID(create_resp.json()["debit"]["transfer_pair_id"])

    delete_resp = await client.delete(
        f"/api/transactions/{debit_id}",
        headers=auth_headers,
    )
    assert delete_resp.status_code in (200, 204)

    result = await session.execute(
        select(Transaction).where(Transaction.transfer_pair_id == pair_id)
    )
    remaining = result.scalars().all()
    # Both legs should be gone
    assert all(str(t.id) not in (debit_id, credit_id) for t in remaining)
