"""Provisões e diferimentos (A8).

Um cronograma reparte um valor em N meses. Cada mês vira uma `AccrualEntry` pendente; ao
chegar a data, `post_entries` cria a transação do mês (débito = despesa provisionada,
crédito = receita diferida reconhecida). Meses de períodos fechados (A5) não são lançados:
ficam `skipped` e são tentados de novo na próxima execução, caso o período seja reaberto.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.account import Account
from app.models.accrual_schedule import AccrualEntry, AccrualSchedule
from app.models.bank_connection import BankConnection
from app.models.category import Category
from app.models.cost_center import CostCenter
from app.models.transaction import Transaction
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.accrual import AccrualScheduleCreate
from app.services import period_close_service as pcs

_CENT = Decimal("0.01")


def _err(code: str, **extra) -> HTTPException:
    return HTTPException(status_code=422, detail={"code": code, **extra})


def _month_count(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def _add_months(first_of_month: date, n: int) -> date:
    idx = first_of_month.year * 12 + (first_of_month.month - 1) + n
    return date(idx // 12, idx % 12 + 1, 1)


def distribute(total: Decimal, periods: int) -> list[Decimal]:
    """Reparte `total` em `periods` parcelas de centavos; o resíduo de arredondamento vai na última."""
    base = (total / periods).quantize(_CENT, rounding=ROUND_HALF_UP)
    amounts = [base] * periods
    amounts[-1] = total - base * (periods - 1)
    return amounts


async def create_schedule(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    data: AccrualScheduleCreate,
) -> AccrualSchedule:
    if data.start_date >= data.end_date:
        raise _err("accrual_invalid_range")
    periods = _month_count(data.start_date, data.end_date)
    if periods <= 0:
        raise _err("accrual_invalid_range")

    account = (
        await session.execute(
            select(Account)
            .outerjoin(BankConnection)
            .where(
                Account.id == data.account_id,
                or_(Account.workspace_id == workspace_id, BankConnection.workspace_id == workspace_id),
            )
        )
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="account_not_found")
    if data.category_id is not None:
        found = await session.execute(
            select(Category.id).where(Category.id == data.category_id, Category.workspace_id == workspace_id)
        )
        if found.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="category_not_found")
    if data.cost_center_id is not None:
        found = await session.execute(
            select(CostCenter.id).where(
                CostCenter.id == data.cost_center_id, CostCenter.workspace_id == workspace_id
            )
        )
        if found.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="cost_center_not_found")
    if data.source_transaction_id is not None:
        found = await session.execute(
            select(Transaction.id).where(
                Transaction.id == data.source_transaction_id, Transaction.workspace_id == workspace_id
            )
        )
        if found.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="transaction_not_found")

    amounts = distribute(data.total_amount, periods)
    first = data.start_date.replace(day=1)
    schedule = AccrualSchedule(
        workspace_id=workspace_id,
        source_transaction_id=data.source_transaction_id,
        description=data.description,
        total_amount=data.total_amount,
        type=data.type,
        category_id=data.category_id,
        cost_center_id=data.cost_center_id,
        account_id=data.account_id,
        start_date=data.start_date,
        end_date=data.end_date,
        period_count=periods,
        amount_per_period=amounts[0],
        currency=(data.currency or account.currency or "BRL").upper(),
        is_active=True,
        created_by_user_id=user_id,
    )
    schedule.entries = [
        AccrualEntry(
            workspace_id=workspace_id,
            period_date=_add_months(first, i),
            amount=amount,
            status="pending",
        )
        for i, amount in enumerate(amounts)
    ]
    session.add(schedule)
    await session.commit()
    return await get_schedule(session, schedule.id, workspace_id)  # type: ignore[return-value]


async def get_schedule(
    session: AsyncSession, schedule_id: uuid.UUID, workspace_id: uuid.UUID
) -> AccrualSchedule | None:
    result = await session.execute(
        select(AccrualSchedule)
        .where(AccrualSchedule.id == schedule_id, AccrualSchedule.workspace_id == workspace_id)
        .options(selectinload(AccrualSchedule.entries))
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def get_schedules(session: AsyncSession, workspace_id: uuid.UUID) -> list[AccrualSchedule]:
    result = await session.execute(
        select(AccrualSchedule)
        .where(AccrualSchedule.workspace_id == workspace_id)
        .options(selectinload(AccrualSchedule.entries))
        .order_by(AccrualSchedule.created_at.desc())
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


def status_counts(schedule: AccrualSchedule) -> dict[str, int]:
    counts = {"posted": 0, "pending": 0, "skipped": 0}
    for entry in schedule.entries:
        counts[entry.status] = counts.get(entry.status, 0) + 1
    return {f"{k}_count": v for k, v in counts.items()}


async def cancel_schedule(
    session: AsyncSession, schedule_id: uuid.UUID, workspace_id: uuid.UUID
) -> AccrualSchedule | None:
    """Encerra o cronograma. O que já foi lançado permanece; o restante deixa de valer."""
    schedule = await get_schedule(session, schedule_id, workspace_id)
    if schedule is None:
        return None
    schedule.is_active = False
    for entry in schedule.entries:
        if entry.status == "pending":
            entry.status = "skipped"
    await session.commit()
    return await get_schedule(session, schedule_id, workspace_id)


async def _fallback_user_id(session: AsyncSession, workspace_id: uuid.UUID) -> uuid.UUID | None:
    result = await session.execute(
        select(WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.role == "owner")
        .limit(1)
    )
    return result.scalar_one_or_none()


async def post_entries(
    session: AsyncSession, workspace_id: uuid.UUID, up_to_date: date
) -> dict[str, int]:
    """Lança as parcelas vencidas (`period_date <= up_to_date`) de cronogramas ativos."""
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        return {"posted": 0, "skipped": 0}

    result = await session.execute(
        select(AccrualEntry)
        .join(AccrualSchedule, AccrualEntry.schedule_id == AccrualSchedule.id)
        .where(
            AccrualEntry.workspace_id == workspace_id,
            AccrualSchedule.is_active.is_(True),
            AccrualEntry.status.in_(("pending", "skipped")),
            AccrualEntry.period_date <= up_to_date,
        )
        .options(selectinload(AccrualEntry.schedule))
        .order_by(AccrualEntry.period_date)
        # Duas execuções simultâneas (beat + botão) não lançam a mesma parcela duas vezes.
        .with_for_update(of=AccrualEntry, skip_locked=True)
    )
    entries = list(result.scalars().all())

    posted = skipped = 0
    fallback_user: uuid.UUID | None = None
    for entry in entries:
        schedule = entry.schedule
        if schedule.account_id is None:  # conta removida: não há onde lançar
            entry.status = "skipped"
            skipped += 1
            continue
        if await pcs.is_period_closed(session, workspace, entry.period_date):
            entry.status = "skipped"
            skipped += 1
            continue

        user_id = schedule.created_by_user_id
        if user_id is None:
            fallback_user = fallback_user or await _fallback_user_id(session, workspace_id)
            user_id = fallback_user
        if user_id is None:
            entry.status = "skipped"
            skipped += 1
            continue

        tx = Transaction(
            user_id=user_id,
            workspace_id=workspace_id,
            account_id=schedule.account_id,
            category_id=schedule.category_id,
            cost_center_id=schedule.cost_center_id,
            description=schedule.description,
            amount=entry.amount,
            currency=schedule.currency,
            date=entry.period_date,
            effective_date=entry.period_date,
            type="debit" if schedule.type == "accrual" else "credit",
            source="accrual",
            status="posted",
            notes=f"{schedule.type} {entry.period_date:%m/%Y}",
        )
        session.add(tx)
        await session.flush()
        entry.transaction_id = tx.id
        entry.status = "posted"
        entry.posted_at = datetime.now(timezone.utc)
        posted += 1

    await session.commit()
    return {"posted": posted, "skipped": skipped}
