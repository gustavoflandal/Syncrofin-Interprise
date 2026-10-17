"""Visão somente leitura das obrigações fiscais.

Obrigação fiscal não é uma entidade nova: é uma recorrência com
``tax_obligation_type``. Estas rotas só filtram e somam; criar e editar
continua em ``/api/recurring-transactions``. Usam ``export.read`` como as
rotas de AP/AR, pois expõem o mesmo tipo de dado financeiro.
"""
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, require_permission
from app.models.recurring_transaction import RecurringTransaction
from app.schemas.ar_ap import CashFlowForecast, TaxObligationSummary
from app.schemas.recurring_transaction import RecurringTransactionRead
from app.services import ar_ap_service
from app.services.recurring_transaction_service import get_occurrences_in_range

router = APIRouter(prefix="/api/tax-obligations", tags=["tax-obligations"])

_read_gate = require_permission("export.read")

ZERO = Decimal("0")


@router.get("", response_model=list[RecurringTransactionRead])
async def list_tax_obligations(
    ctx: WorkspaceContext = Depends(_read_gate),
    session: AsyncSession = Depends(get_async_session),
):
    result = await session.execute(
        select(RecurringTransaction)
        .where(
            RecurringTransaction.workspace_id == ctx.workspace.id,
            RecurringTransaction.tax_obligation_type.isnot(None),
        )
        .order_by(RecurringTransaction.description)
    )
    return result.scalars().all()


@router.get("/summary", response_model=TaxObligationSummary)
async def tax_obligations_summary(
    ctx: WorkspaceContext = Depends(_read_gate),
    session: AsyncSession = Depends(get_async_session),
):
    today = date.today()
    month_start = today.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)

    obligations = (
        await session.execute(
            select(RecurringTransaction).where(
                RecurringTransaction.workspace_id == ctx.workspace.id,
                RecurringTransaction.is_active.is_(True),
                RecurringTransaction.tax_obligation_type.isnot(None),
            )
        )
    ).scalars().all()

    by_type: dict[str, Decimal] = {}
    for rt in obligations:
        # Conta cada ocorrência do mês (uma recorrência semanal cai várias vezes).
        occurrences = get_occurrences_in_range(
            rt.start_date, rt.frequency, rt.end_date,
            month_start, month_end,
            intended_day=rt.day_of_month,
            weekend_adjustment=rt.weekend_adjustment,
        )
        if occurrences:
            key = rt.tax_obligation_type
            by_type[key] = by_type.get(key, ZERO) + rt.amount * len(occurrences)

    return TaxObligationSummary(
        month=month_start, total=sum(by_type.values(), ZERO), by_type=by_type
    )


@router.get("/forecast", response_model=CashFlowForecast)
async def tax_obligations_forecast(
    currency: str = Query("BRL", max_length=3),
    period: Literal["week", "month"] = Query("month"),
    num_buckets: int = Query(12, ge=1, le=52),
    ctx: WorkspaceContext = Depends(_read_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """Mesmo fluxo de caixa de AP/AR; o campo ``taxes`` de cada balde traz as obrigações."""
    return await ar_ap_service.get_forecast(
        session,
        ctx.workspace.id,
        currency=currency.upper(),
        period=period,
        num_buckets=num_buckets,
    )
