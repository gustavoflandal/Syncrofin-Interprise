"""Tests for consolidated multi-workspace DRE service (A7)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workspace import Workspace, WorkspaceMember
from app.services import consolidated_service


async def _make_workspace(session: AsyncSession, *, user_id: uuid.UUID, name: str = "WS") -> Workspace:
    ws = Workspace(
        id=uuid.uuid4(),
        name=name,
        kind="business",
        created_by_user_id=user_id,
        default_currency="BRL",
        locale="pt-BR",
    )
    session.add(ws)
    await session.flush()
    session.add(WorkspaceMember(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        user_id=user_id,
        role="owner",
    ))
    await session.flush()
    return ws


@pytest.mark.asyncio
async def test_requires_at_least_one_workspace(session: AsyncSession, clean_db):
    user_id = uuid.uuid4()
    with pytest.raises(ValueError, match="At least one"):
        await consolidated_service.get_consolidated_dre(session, [], user_id, 2026, 1)


@pytest.mark.asyncio
async def test_forbids_non_member_workspace(session: AsyncSession, clean_db, test_user):
    ws_other = Workspace(
        id=uuid.uuid4(), name="Other", kind="business",
        created_by_user_id=uuid.uuid4(), default_currency="BRL", locale="pt-BR",
    )
    session.add(ws_other)
    await session.commit()

    with pytest.raises(ValueError, match="Not a member"):
        await consolidated_service.get_consolidated_dre(
            session, [ws_other.id, uuid.uuid4()], test_user.id, 2026, 1
        )


@pytest.mark.asyncio
async def test_consolidated_empty_workspaces(session: AsyncSession, clean_db, test_user):
    ws1 = await _make_workspace(session, user_id=test_user.id, name="Empresa A")
    ws2 = await _make_workspace(session, user_id=test_user.id, name="Empresa B")
    await session.commit()

    result = await consolidated_service.get_consolidated_dre(
        session, [ws1.id, ws2.id], test_user.id, 2026, 1
    )

    assert result.year == 2026
    assert result.month == 1
    assert len(result.workspace_reports) == 2
    assert result.consolidated.result == Decimal(0)
    names = {ws.workspace_name for ws in result.workspace_reports}
    assert names == {"Empresa A", "Empresa B"}


@pytest.mark.asyncio
async def test_consolidated_aggregates_revenues(session: AsyncSession, clean_db, test_user):
    """Revenues from two workspaces should add up in the consolidated report."""
    from datetime import date
    from decimal import Decimal
    from app.models.account import Account
    from app.models.transaction import Transaction
    from app.models.category import Category

    ws1 = await _make_workspace(session, user_id=test_user.id, name="Filial A")
    ws2 = await _make_workspace(session, user_id=test_user.id, name="Filial B")

    # Category in ws1
    cat1 = Category(id=uuid.uuid4(), workspace_id=ws1.id, name="Vendas", type="credit")
    session.add(cat1)
    # Account in ws1
    acc1 = Account(
        id=uuid.uuid4(), workspace_id=ws1.id, user_id=test_user.id,
        name="Caixa A", currency="BRL", type="checking",
    )
    session.add(acc1)
    await session.flush()

    # Category in ws2
    cat2 = Category(id=uuid.uuid4(), workspace_id=ws2.id, name="Vendas", type="credit")
    session.add(cat2)
    acc2 = Account(
        id=uuid.uuid4(), workspace_id=ws2.id, user_id=test_user.id,
        name="Caixa B", currency="BRL", type="checking",
    )
    session.add(acc2)
    await session.flush()

    # Transaction in ws1: +1000
    session.add(Transaction(
        id=uuid.uuid4(), workspace_id=ws1.id, user_id=test_user.id,
        account_id=acc1.id, category_id=cat1.id,
        type="credit", amount=Decimal("1000"), date=date(2026, 1, 15),
        description="Venda A", status="posted",
    ))
    # Transaction in ws2: +500
    session.add(Transaction(
        id=uuid.uuid4(), workspace_id=ws2.id, user_id=test_user.id,
        account_id=acc2.id, category_id=cat2.id,
        type="credit", amount=Decimal("500"), date=date(2026, 1, 15),
        description="Venda B", status="posted",
    ))
    await session.commit()

    result = await consolidated_service.get_consolidated_dre(
        session, [ws1.id, ws2.id], test_user.id, 2026, 1
    )

    assert result.consolidated.gross_revenue == Decimal("1500")
    assert result.consolidated.result == Decimal("1500")
