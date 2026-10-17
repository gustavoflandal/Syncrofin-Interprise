"""AP/AR overview, title list, cash-flow forecast and NF-e XML import routes."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.upload_guard import validate_upload
from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, require_permission
from app.models.invoice import Invoice
from app.schemas.ar_ap import (
    ArApOverview,
    CashFlowForecast,
    NfeImportResult,
    TitleRead,
    TitlesPage,
)
from app.services import ar_ap_service
from app.services.invoice_service import balance as _balance, days_overdue, derive_state

router = APIRouter(prefix="/api/ar-ap", tags=["ar-ap"])

_read_gate = require_permission("export.read")
_write_gate = require_permission("invoices.write")


def _serialize_title(inv: Invoice) -> TitleRead:
    return TitleRead(
        id=inv.id,
        direction=inv.direction,
        state=derive_state(inv),
        number=inv.number,
        series=inv.series,
        external_number=getattr(inv, "external_number", None),
        issue_date=inv.issue_date,
        due_date=inv.due_date,
        currency=inv.currency or "BRL",
        total=inv.total,
        balance=_balance(inv),
        days_overdue=days_overdue(inv),
        payee_id=inv.payee_id,
        payee_name=inv.payee.name if inv.payee else None,
    )


@router.get("/overview", response_model=ArApOverview)
async def get_overview(
    ctx: WorkspaceContext = Depends(_read_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """Snapshot of open receivables, payables and net position."""
    return await ar_ap_service.get_overview(session, ctx.workspace.id)


@router.get("/titles", response_model=TitlesPage)
async def list_titles(
    direction: Literal["receivable", "payable"] = Query("receivable"),
    state: Optional[str] = Query(None, description="open | overdue | paid | draft | all"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    ctx: WorkspaceContext = Depends(_read_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """Paginated list of titles (invoices) for one side of the ledger."""
    items, total = await ar_ap_service.list_titles(
        session,
        ctx.workspace.id,
        direction=direction,
        state_filter=state,
        page=page,
        page_size=page_size,
    )
    return TitlesPage(
        items=[_serialize_title(inv) for inv in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/forecast", response_model=CashFlowForecast)
async def get_forecast(
    currency: str = Query("BRL", max_length=3),
    period: Literal["week", "month"] = Query("month"),
    num_buckets: int = Query(12, ge=1, le=52),
    ctx: WorkspaceContext = Depends(_read_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """Cash-flow forecast grouped by week or month for the next N buckets."""
    return await ar_ap_service.get_forecast(
        session,
        ctx.workspace.id,
        currency=currency.upper(),
        period=period,
        num_buckets=num_buckets,
    )


@router.post("/import/nfe", response_model=NfeImportResult)
async def import_nfe(
    files: list[UploadFile] = File(..., description="Arquivos XML de NF-e (máx. 50 por envio)"),
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """Importa um ou mais XMLs de NF-e como títulos a pagar.

    Cada arquivo é processado de forma independente: arquivos inválidos
    geram uma linha ``status="error"`` sem abortar os demais. Chaves de
    acesso já importadas retornam ``status="duplicate"``.
    """
    if len(files) > 50:
        raise HTTPException(status_code=422, detail="Máximo de 50 arquivos por envio")

    file_data: list[tuple[str, bytes]] = []
    for f in files:
        content, _ = await validate_upload(f, category="import")
        file_data.append((f.filename or "desconhecido.xml", content))

    return await ar_ap_service.import_nfe_files(
        session,
        ctx.workspace.id,
        ctx.user.id,
        file_data,
    )
