"""API pública versionada — SyncroFin Enterprise v1 (F1).

Contrato estável para integradores externos. O frontend continua usando os
endpoints internos em /api/*; esta camada expõe o subconjunto mais comum com:

  - Prefixo /api/v1
  - Paginação cursor-offset uniforme (page + limit + total + items)
  - Respostas mínimas e estáveis (sem campos internos voláteis)
  - Documentação separada em /api/v1/docs

Recursos estáveis:
  GET  /api/v1/workspaces
  GET  /api/v1/workspaces/{id}
  GET  /api/v1/workspaces/{id}/accounts
  GET  /api/v1/workspaces/{id}/transactions
  GET  /api/v1/workspaces/{id}/payees
  GET  /api/v1/workspaces/{id}/invoices
  GET  /api/v1/workspaces/{id}/categories

Autenticação: Bearer token (API Key obtida em Configurações → Tokens de API).
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.auth import current_active_user
from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, current_workspace
from app.models.account import Account
from app.models.category import Category
from app.models.workspace import Workspace
from app.schemas.user import UserRead

router = APIRouter(prefix="/api/v1", tags=["v1"])


# ─── Stable response schemas ────────────────────────────────────────────────

class V1Page(BaseModel):
    """Paginated response envelope (stable)."""
    items: list[Any]
    total: int
    page: int
    limit: int


class V1WorkspaceOut(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    default_currency: str
    locale: str


class V1AccountOut(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    currency: str
    balance: Decimal
    institution: Optional[str] = None


class V1TransactionOut(BaseModel):
    id: uuid.UUID
    date: date
    description: str
    amount: Decimal
    currency: str
    type: str
    status: str
    account_id: uuid.UUID
    category_id: Optional[uuid.UUID] = None
    payee_id: Optional[uuid.UUID] = None


class V1InvoiceOut(BaseModel):
    id: uuid.UUID
    number: Optional[str] = None
    direction: str
    status: str
    total: Decimal
    currency: str
    due_date: Optional[date] = None
    payee_id: Optional[uuid.UUID] = None


class V1PayeeOut(BaseModel):
    id: uuid.UUID
    name: str
    email: Optional[str] = None


class V1CategoryOut(BaseModel):
    id: uuid.UUID
    name: str
    group_id: Optional[uuid.UUID] = None
    is_hidden: bool = False


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.get(
    "/workspaces",
    response_model=list[V1WorkspaceOut],
    summary="List workspaces",
    description="Returns the workspaces the authenticated user is a member of.",
)
async def v1_list_workspaces(
    user: UserRead = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
) -> list[V1WorkspaceOut]:
    from app.models.workspace import WorkspaceMembership
    rows = await session.execute(
        select(Workspace)
        .join(WorkspaceMembership, Workspace.id == WorkspaceMembership.workspace_id)
        .where(WorkspaceMembership.user_id == user.id, Workspace.is_archived.is_(False))
        .order_by(Workspace.name)
    )
    return [
        V1WorkspaceOut(
            id=w.id,
            name=w.name,
            kind=w.kind.value if hasattr(w.kind, "value") else w.kind,
            default_currency=w.default_currency or "BRL",
            locale=w.locale or "pt-BR",
        )
        for w in rows.scalars()
    ]


@router.get(
    "/workspaces/{workspace_id}",
    response_model=V1WorkspaceOut,
    summary="Get workspace",
)
async def v1_get_workspace(
    workspace_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
) -> V1WorkspaceOut:
    w = ctx.workspace
    if w.id != workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return V1WorkspaceOut(
        id=w.id,
        name=w.name,
        kind=w.kind.value if hasattr(w.kind, "value") else w.kind,
        default_currency=w.default_currency or "BRL",
        locale=w.locale or "pt-BR",
    )


@router.get(
    "/workspaces/{workspace_id}/accounts",
    response_model=list[V1AccountOut],
    summary="List accounts",
)
async def v1_list_accounts(
    workspace_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
) -> list[V1AccountOut]:
    rows = await session.execute(
        select(Account)
        .where(Account.workspace_id == workspace_id, Account.is_closed.is_(False))
        .order_by(Account.name)
    )
    return [
        V1AccountOut(
            id=a.id,
            name=a.name,
            type=a.type,
            currency=a.currency or ctx.workspace.default_currency or "BRL",
            balance=a.balance or Decimal("0"),
            institution=a.institution.name if a.institution else None,
        )
        for a in rows.scalars()
    ]


@router.get(
    "/workspaces/{workspace_id}/transactions",
    response_model=V1Page,
    summary="List transactions",
    description=(
        "Paginated list of transactions. Filters: `from` (YYYY-MM-DD), `to` (YYYY-MM-DD), "
        "`account_id`, `type` (debit|credit), `status` (posted|pending)."
    ),
)
async def v1_list_transactions(
    workspace_id: uuid.UUID,
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    account_id: Optional[uuid.UUID] = Query(None),
    type: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
) -> V1Page:
    from app.services import transaction_service
    transactions, total, _ = await transaction_service.get_transactions(
        session,
        workspace_id,
        ctx.user_id,
        account_ids=[account_id] if account_id else None,
        from_date=from_date,
        to_date=to_date,
        page=page,
        limit=limit,
        txn_type=type,
        status=status_,
        include_summary=False,
    )
    items = [
        V1TransactionOut(
            id=tx.id,
            date=tx.date,
            description=tx.description or "",
            amount=Decimal(str(tx.amount or 0)),
            currency=tx.currency or ctx.workspace.default_currency or "BRL",
            type=tx.type,
            status=tx.status or "posted",
            account_id=tx.account_id,
            category_id=tx.category_id,
            payee_id=tx.payee_id,
        )
        for tx in transactions
    ]
    return V1Page(items=items, total=total, page=page, limit=limit)


@router.get(
    "/workspaces/{workspace_id}/invoices",
    response_model=V1Page,
    summary="List invoices",
    description="Paginated list of invoices (A/R and A/P). Filter by `status` (draft|open|partial|paid|cancelled|void).",
)
async def v1_list_invoices(
    workspace_id: uuid.UUID,
    status_: Optional[str] = Query(None, alias="status"),
    direction: Optional[str] = Query(None, description="accounts_receivable | accounts_payable"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
) -> V1Page:
    from app.models.invoice import Invoice
    q = select(Invoice).where(Invoice.workspace_id == workspace_id)
    if status_:
        q = q.where(Invoice.status == status_)
    if direction:
        q = q.where(Invoice.direction == direction)
    total_q = select(Invoice).where(Invoice.workspace_id == workspace_id)
    if status_:
        total_q = total_q.where(Invoice.status == status_)
    if direction:
        total_q = total_q.where(Invoice.direction == direction)
    from sqlalchemy import func
    count_row = await session.scalar(select(func.count()).select_from(total_q.subquery()))
    total = count_row or 0
    q = q.order_by(Invoice.due_date.desc().nulls_last()).offset((page - 1) * limit).limit(limit)
    rows = await session.execute(q)
    items = [
        V1InvoiceOut(
            id=inv.id,
            number=str(inv.number) if inv.number else inv.external_number,
            direction=inv.direction,
            status=inv.status,
            total=inv.total or Decimal("0"),
            currency=inv.currency or ctx.workspace.default_currency or "BRL",
            due_date=inv.due_date,
            payee_id=inv.payee_id,
        )
        for inv in rows.scalars()
    ]
    return V1Page(items=items, total=total, page=page, limit=limit)


@router.get(
    "/workspaces/{workspace_id}/payees",
    response_model=list[V1PayeeOut],
    summary="List payees",
)
async def v1_list_payees(
    workspace_id: uuid.UUID,
    q: Optional[str] = Query(None, description="Search by name"),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
) -> list[V1PayeeOut]:
    from app.models.payee import Payee
    stmt = select(Payee).where(Payee.workspace_id == workspace_id)
    if q:
        stmt = stmt.where(Payee.name.ilike(f"%{q}%"))
    stmt = stmt.order_by(Payee.name).limit(200)
    rows = await session.execute(stmt)
    return [
        V1PayeeOut(id=p.id, name=p.name, email=getattr(p, "email", None))
        for p in rows.scalars()
    ]


@router.get(
    "/workspaces/{workspace_id}/categories",
    response_model=list[V1CategoryOut],
    summary="List categories",
)
async def v1_list_categories(
    workspace_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
) -> list[V1CategoryOut]:
    rows = await session.execute(
        select(Category)
        .where(Category.workspace_id == workspace_id)
        .order_by(Category.name)
    )
    return [
        V1CategoryOut(id=c.id, name=c.name, group_id=c.group_id, is_hidden=c.is_hidden)
        for c in rows.scalars()
    ]


@router.get("/info", summary="API version info")
async def v1_info() -> dict:
    return {
        "version": "1",
        "status": "stable",
        "docs": "/api/v1/docs",
        "openapi": "/api/v1/openapi.json",
        "resources": [
            "workspaces",
            "workspaces/{id}/accounts",
            "workspaces/{id}/transactions",
            "workspaces/{id}/invoices",
            "workspaces/{id}/payees",
            "workspaces/{id}/categories",
        ],
        "pagination": {
            "style": "offset",
            "params": ["page", "limit"],
            "max_limit": 200,
            "response_envelope": {"items": "list", "total": "int", "page": "int", "limit": "int"},
        },
        "authentication": "Bearer <api_token>",
        "changelog_url": "https://github.com/gustavoflandal/syncrofin-enterprise/blob/main/docs/API_CHANGELOG.md",
    }
