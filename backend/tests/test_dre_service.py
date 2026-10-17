"""Tests for get_dre and get_dfc in report_service.

Uses a real PostgreSQL database (via the shared session fixture from conftest.py).
Local fixtures scope fixtures to this module to avoid polluting the global conftest.
"""
import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.category import Category
from app.models.category_group import CategoryGroup
from app.models.cost_center import CostCenter
from app.models.transaction import Transaction
from app.models.workspace import Workspace, WorkspaceMember
from app.services import report_service

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Local fixtures — scoped to this module
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def user(test_user):
    """Alias for the global test_user fixture."""
    return test_user


@pytest_asyncio.fixture
async def workspace(session: AsyncSession, user) -> Workspace:
    ws = Workspace(
        id=uuid.uuid4(),
        name="Empresa DRE",
        kind="business",
        created_by_user_id=user.id,
        default_currency="BRL",
    )
    session.add(ws)
    await session.flush()
    session.add(
        WorkspaceMember(
            id=uuid.uuid4(),
            workspace_id=ws.id,
            user_id=user.id,
            role="owner",
        )
    )
    await session.flush()
    return ws


@pytest_asyncio.fixture
async def account(session: AsyncSession, workspace: Workspace, user) -> Account:
    acc = Account(
        id=uuid.uuid4(),
        user_id=user.id,
        workspace_id=workspace.id,
        name="Conta Principal",
        type="checking",
        currency="BRL",
    )
    session.add(acc)
    await session.flush()
    return acc


@pytest_asyncio.fixture
async def category_income(session: AsyncSession, user) -> Category:
    cat = Category(
        id=uuid.uuid4(),
        user_id=user.id,
        name="Receitas",
        icon="💰",
        color="#22C55E",
    )
    session.add(cat)
    await session.flush()
    return cat


@pytest_asyncio.fixture
async def category_expense(session: AsyncSession, user) -> Category:
    cat = Category(
        id=uuid.uuid4(),
        user_id=user.id,
        name="Despesas",
        icon="💸",
        color="#EF4444",
    )
    session.add(cat)
    await session.flush()
    return cat


@pytest_asyncio.fixture
async def transfer_category(session: AsyncSession, user) -> Category:
    """Category flagged as treat_as_transfer — excluded from P&L by counts_as_pnl."""
    cat = Category(
        id=uuid.uuid4(),
        user_id=user.id,
        name="Transferências",
        icon="↔️",
        color="#6366F1",
        treat_as_transfer=True,
    )
    session.add(cat)
    await session.flush()
    return cat


# ---------------------------------------------------------------------------
# DRE tests
# ---------------------------------------------------------------------------


async def test_dre_empty_month(session: AsyncSession, workspace: Workspace, user):
    """An empty month returns all zeros."""
    report = await report_service.get_dre(
        session, workspace.id, user.id, 2026, 1
    )
    assert report.gross_revenue == Decimal("0")
    assert report.operating_expenses == Decimal("0")
    assert report.result == Decimal("0")
    assert report.currency == "BRL"
    # prev_month is also computed (with include_prev=True by default)
    assert report.prev_month is not None
    assert report.prev_month.gross_revenue == Decimal("0")


async def test_dre_revenue_and_expense(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
    category_income: Category,
    category_expense: Category,
):
    """Revenue and expense transactions are correctly aggregated."""
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            category_id=category_income.id,
            type="credit",
            amount=Decimal("5000"),
            date=date(2026, 1, 15),
            currency="BRL",
            description="Receita jan",
            source="manual",
        )
    )
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            category_id=category_expense.id,
            type="debit",
            amount=Decimal("1500"),
            date=date(2026, 1, 20),
            currency="BRL",
            description="Despesa jan",
            source="manual",
        )
    )
    await session.flush()

    report = await report_service.get_dre(
        session, workspace.id, user.id, 2026, 1
    )
    assert report.gross_revenue == Decimal("5000")
    assert report.operating_expenses == Decimal("1500")
    assert report.result == Decimal("3500")
    assert report.net_revenue == Decimal("5000")
    assert report.deductions == Decimal("0")


async def test_dre_excludes_transfers(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
    transfer_category: Category,
):
    """Transactions in a treat_as_transfer category are excluded from DRE."""
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            category_id=transfer_category.id,
            type="credit",
            amount=Decimal("2000"),
            date=date(2026, 1, 10),
            currency="BRL",
            description="Transferência",
            source="manual",
        )
    )
    await session.flush()

    report = await report_service.get_dre(
        session, workspace.id, user.id, 2026, 1
    )
    assert report.gross_revenue == Decimal("0")
    assert report.operating_expenses == Decimal("0")


async def test_dre_excludes_opening_balance(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
):
    """Opening balance transactions are not counted in DRE."""
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            type="credit",
            amount=Decimal("10000"),
            date=date(2026, 1, 1),
            currency="BRL",
            description="Saldo inicial",
            source="opening_balance",
        )
    )
    await session.flush()

    report = await report_service.get_dre(
        session, workspace.id, user.id, 2026, 1
    )
    assert report.gross_revenue == Decimal("0")


async def test_dre_sections_detail(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
    category_income: Category,
    category_expense: Category,
):
    """Sections contain one entry per category (fallback natureza: credit→receita, debit→despesa)."""
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            category_id=category_income.id,
            type="credit",
            amount=Decimal("3000"),
            date=date(2026, 2, 5),
            currency="BRL",
            description="Venda",
            source="manual",
        )
    )
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            category_id=category_expense.id,
            type="debit",
            amount=Decimal("500"),
            date=date(2026, 2, 10),
            currency="BRL",
            description="Aluguel",
            source="manual",
        )
    )
    await session.flush()

    report = await report_service.get_dre(
        session, workspace.id, user.id, 2026, 2
    )
    section_keys = {s.key for s in report.sections}
    assert "receita" in section_keys
    assert "despesa" in section_keys

    all_labels = {
        line.label
        for sec in report.sections
        for grp in sec.groups
        for line in grp.lines
    }
    # category names land as line labels (fallback path — no groups)
    assert "Receitas" in all_labels
    assert "Despesas" in all_labels


async def test_dre_amount_primary_takes_precedence(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
):
    """When amount_primary is set, it is used instead of amount."""
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            type="credit",
            amount=Decimal("100"),       # USD amount (original currency)
            amount_primary=Decimal("550"),  # BRL equivalent
            date=date(2026, 3, 1),
            currency="USD",
            description="Exportação",
            source="manual",
        )
    )
    await session.flush()

    report = await report_service.get_dre(
        session, workspace.id, user.id, 2026, 3
    )
    assert report.gross_revenue == Decimal("550")


# ---------------------------------------------------------------------------
# DFC tests
# ---------------------------------------------------------------------------


async def test_dfc_empty_month(session: AsyncSession, workspace: Workspace, user):
    """An empty month returns zero balances and no periods."""
    report = await report_service.get_dfc(
        session, workspace.id, user.id, 2026, 4
    )
    assert report.opening_balance == Decimal("0")
    assert report.closing_balance == Decimal("0")
    assert report.periods == []
    assert report.currency == "BRL"


async def test_dfc_weekly_grouping(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
):
    """Transactions are grouped by ISO week (Monday-based)."""
    # Week 1 of January 2026: Jan 5 (Mon) – Jan 11 (Sun)
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            type="credit",
            amount=Decimal("1000"),
            date=date(2026, 1, 7),   # Wednesday
            currency="BRL",
            description="Entrada semana 1",
            source="manual",
        )
    )
    # Week 2: Jan 12 (Mon) – Jan 18 (Sun)
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            type="debit",
            amount=Decimal("300"),
            date=date(2026, 1, 14),  # Wednesday
            currency="BRL",
            description="Saída semana 2",
            source="manual",
        )
    )
    await session.flush()

    report = await report_service.get_dfc(
        session, workspace.id, user.id, 2026, 1
    )
    assert len(report.periods) == 2
    week1 = report.periods[0]
    week2 = report.periods[1]
    assert week1.inflows == Decimal("1000")
    assert week1.outflows == Decimal("0")
    assert week2.inflows == Decimal("0")
    assert week2.outflows == Decimal("300")
    assert report.closing_balance == Decimal("700")


async def test_dre_excludes_pending(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
    category_income: Category,
):
    """Pending transactions must not appear in the DRE (only posted ones count)."""
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            category_id=category_income.id,
            date=date(2026, 1, 15),
            amount=Decimal("500.00"),
            type="credit",
            status="pending",  # deve ser excluído
            description="pending income",
            source="manual",
            currency="BRL",
        )
    )
    await session.flush()
    report = await report_service.get_dre(session, workspace.id, user.id, 2026, 1)
    assert report.gross_revenue == Decimal("0")


async def test_dfc_opening_balance_uses_prior_transactions(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
):
    """Transactions before the month contribute to opening_balance."""
    # December 2025 — prior to the report month (January 2026)
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            type="credit",
            amount=Decimal("5000"),
            date=date(2025, 12, 15),
            currency="BRL",
            description="Receita dezembro",
            source="manual",
        )
    )
    await session.flush()

    report = await report_service.get_dfc(
        session, workspace.id, user.id, 2026, 1
    )
    assert report.opening_balance == Decimal("5000")


# ---------------------------------------------------------------------------
# Seções com natureza via CategoryGroup
# ---------------------------------------------------------------------------


async def test_dre_sections_use_group_natureza(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
):
    """Quando a categoria tem grupo com natureza, o DRE usa essa natureza."""
    grp = CategoryGroup(
        workspace_id=workspace.id,
        user_id=user.id,
        name="Serviços",
        natureza="receita",
        depth=0,
    )
    session.add(grp)
    await session.flush()

    cat = Category(
        id=uuid.uuid4(),
        user_id=user.id,
        workspace_id=workspace.id,
        name="Consultoria",
        group_id=grp.id,
    )
    session.add(cat)
    await session.flush()

    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            category_id=cat.id,
            type="credit",
            amount=Decimal("8000"),
            date=date(2026, 5, 10),
            currency="BRL",
            description="Projeto A",
            source="manual",
        )
    )
    await session.flush()

    report = await report_service.get_dre(session, workspace.id, user.id, 2026, 5)
    assert any(s.key == "receita" for s in report.sections)
    receita_sec = next(s for s in report.sections if s.key == "receita")
    assert any(g.group_name == "Serviços" for g in receita_sec.groups)
    assert report.gross_revenue == Decimal("8000")


async def test_dre_sections_inherit_natureza_from_parent(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
):
    """Subgrupo sem natureza herda do grupo pai."""
    parent = CategoryGroup(
        workspace_id=workspace.id,
        user_id=user.id,
        name="Custos",
        natureza="custo",
        depth=0,
    )
    session.add(parent)
    await session.flush()

    child = CategoryGroup(
        workspace_id=workspace.id,
        user_id=user.id,
        name="Insumos",
        natureza=None,
        parent_id=parent.id,
        depth=1,
    )
    session.add(child)
    await session.flush()

    cat = Category(
        id=uuid.uuid4(),
        user_id=user.id,
        workspace_id=workspace.id,
        name="Matéria-prima",
        group_id=child.id,
    )
    session.add(cat)
    await session.flush()

    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            category_id=cat.id,
            type="debit",
            amount=Decimal("2000"),
            date=date(2026, 6, 1),
            currency="BRL",
            description="Compra insumos",
            source="manual",
        )
    )
    await session.flush()

    report = await report_service.get_dre(session, workspace.id, user.id, 2026, 6)
    assert any(s.key == "custo" for s in report.sections)


# ---------------------------------------------------------------------------
# Filtro por centro de custo
# ---------------------------------------------------------------------------


async def test_dre_cost_center_filter(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
    category_income: Category,
):
    """Com cost_center_id, apenas transações daquele CC aparecem no DRE."""
    cc = CostCenter(workspace_id=workspace.id, name="Loja A", code="LA")
    session.add(cc)
    await session.flush()

    # transação no CC
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            category_id=category_income.id,
            cost_center_id=cc.id,
            type="credit",
            amount=Decimal("1500"),
            date=date(2026, 7, 5),
            currency="BRL",
            description="Venda loja A",
            source="manual",
        )
    )
    # transação sem CC — não deve aparecer
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            category_id=category_income.id,
            type="credit",
            amount=Decimal("9999"),
            date=date(2026, 7, 6),
            currency="BRL",
            description="Venda geral",
            source="manual",
        )
    )
    await session.flush()

    report = await report_service.get_dre(
        session, workspace.id, user.id, 2026, 7, cost_center_id=cc.id
    )
    assert report.gross_revenue == Decimal("1500")
    assert report.cost_center_id == cc.id


async def test_dre_cost_center_wrong_workspace_raises(
    session: AsyncSession,
    workspace: Workspace,
    user,
):
    """CC de workspace diferente → HTTPException 404."""
    from fastapi import HTTPException

    other_ws = Workspace(
        id=uuid.uuid4(),
        name="Outro WS",
        kind="personal",
        created_by_user_id=user.id,
        default_currency="BRL",
    )
    session.add(other_ws)
    await session.flush()

    cc_other = CostCenter(workspace_id=other_ws.id, name="Externo", code="EXT")
    session.add(cc_other)
    await session.flush()

    with pytest.raises(HTTPException) as exc:
        await report_service.get_dre(
            session, workspace.id, user.id, 2026, 8, cost_center_id=cc_other.id
        )
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# DRE trimestral e anual
# ---------------------------------------------------------------------------


async def test_get_dre_quarterly_aggregates_three_months(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
    category_income: Category,
):
    """get_dre_quarterly soma os 3 meses do trimestre."""
    for month, amount in [(1, Decimal("1000")), (2, Decimal("2000")), (3, Decimal("3000"))]:
        session.add(
            Transaction(
                workspace_id=workspace.id,
                user_id=user.id,
                account_id=account.id,
                category_id=category_income.id,
                type="credit",
                amount=amount,
                date=date(2026, month, 15),
                currency="BRL",
                description=f"Receita mês {month}",
                source="manual",
            )
        )
    await session.flush()

    report = await report_service.get_dre_quarterly(
        session, workspace.id, user.id, 2026, 1
    )
    assert report.year == 2026
    assert report.quarter == 1
    assert len(report.months) == 3
    assert report.gross_revenue == Decimal("6000")


async def test_get_dre_annual_has_twelve_months(
    session: AsyncSession,
    workspace: Workspace,
    user,
):
    """get_dre_annual retorna exatamente 12 meses."""
    report = await report_service.get_dre_annual(
        session, workspace.id, user.id, 2026
    )
    assert report.year == 2026
    assert len(report.monthly) == 12


# ---------------------------------------------------------------------------
# A4 novos parâmetros: accounting_mode e show_budget
# ---------------------------------------------------------------------------


async def test_dre_accounting_mode_competence_vs_cash(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
    category_income: Category,
):
    """accounting_mode='cash' usa effective_date; 'competence' usa date."""
    # Transação com date em jan/2026 mas effective_date em fev/2026
    tx = Transaction(
        workspace_id=workspace.id,
        user_id=user.id,
        account_id=account.id,
        category_id=category_income.id,
        type="credit",
        amount=Decimal("2000"),
        date=date(2026, 1, 20),
        effective_date=date(2026, 2, 5),
        currency="BRL",
        description="Fatura cartão",
        source="manual",
    )
    session.add(tx)
    await session.flush()

    report_comp = await report_service.get_dre(
        session, workspace.id, user.id, 2026, 1,
        accounting_mode="competence",
    )
    # Competência: date=jan → aparece em janeiro
    assert report_comp.gross_revenue == Decimal("2000")

    report_cash = await report_service.get_dre(
        session, workspace.id, user.id, 2026, 1,
        accounting_mode="cash",
    )
    # Caixa: effective_date=fev → não aparece em janeiro
    assert report_cash.gross_revenue == Decimal("0")

    report_cash_feb = await report_service.get_dre(
        session, workspace.id, user.id, 2026, 2,
        accounting_mode="cash",
    )
    # Caixa: effective_date=fev → aparece em fevereiro
    assert report_cash_feb.gross_revenue == Decimal("2000")


async def test_dre_accounting_mode_propagates_to_quarterly(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
    category_income: Category,
):
    """accounting_mode é propagado ao get_dre_quarterly."""
    tx = Transaction(
        workspace_id=workspace.id,
        user_id=user.id,
        account_id=account.id,
        category_id=category_income.id,
        type="credit",
        amount=Decimal("1000"),
        date=date(2026, 1, 10),
        effective_date=date(2026, 4, 10),
        currency="BRL",
        description="Pagamento Q2",
        source="manual",
    )
    session.add(tx)
    await session.flush()

    report_comp = await report_service.get_dre_quarterly(
        session, workspace.id, user.id, 2026, 1,
        accounting_mode="competence",
    )
    # Competência: date=jan → Q1 inclui
    assert report_comp.gross_revenue == Decimal("1000")

    report_cash = await report_service.get_dre_quarterly(
        session, workspace.id, user.id, 2026, 1,
        accounting_mode="cash",
    )
    # Caixa: effective_date=abr → Q1 não inclui
    assert report_cash.gross_revenue == Decimal("0")


async def test_dre_show_budget_returns_budgeted_field(
    session: AsyncSession,
    workspace: Workspace,
    user,
    account: Account,
    category_income: Category,
):
    """show_budget=True não quebra — report retorna sem erro mesmo sem orçamento."""
    session.add(
        Transaction(
            workspace_id=workspace.id,
            user_id=user.id,
            account_id=account.id,
            category_id=category_income.id,
            type="credit",
            amount=Decimal("3000"),
            date=date(2026, 1, 15),
            currency="BRL",
            description="Receita com orçamento",
            source="manual",
        )
    )
    await session.flush()

    report = await report_service.get_dre(
        session, workspace.id, user.id, 2026, 1,
        show_budget=True,
    )
    # Sem orçamento cadastrado: budget_result pode ser None ou zero — não deve falhar
    assert report.gross_revenue == Decimal("3000")
    assert report.accounting_mode == "competence"
