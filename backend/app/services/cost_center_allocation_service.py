"""Rateio de uma transação entre centros de custo (A8).

Invariante: se a transação tem alocações, elas somam exatamente `transaction.amount`.
Sem alocações vale `transaction.cost_center_id` (legado). Ao ratear, `cost_center_id`
passa a apontar para o centro de maior fatia — assim filtros e orçamentos antigos, que só
olham essa coluna, continuam com uma resposta razoável; os relatórios, porém, usam as fatias.
"""
from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.cost_center import CostCenter
from app.models.cost_center_allocation import CostCenterAllocation
from app.models.transaction import Transaction
from app.models.workspace import Workspace

_CENT = Decimal("0.01")
_PCT = Decimal("0.0001")
_HUNDRED = Decimal("100")
# Diferença tolerada ao somar percentuais digitados (33,33 + 33,33 + 33,33): o resíduo vai na última fatia.
_PCT_TOLERANCE = Decimal("0.01")


def _err(code: str, status: int = 422, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, **extra})


def _cents(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


async def _load_transaction(
    session: AsyncSession, transaction_id: uuid.UUID, workspace_id: uuid.UUID
) -> Transaction:
    result = await session.execute(
        select(Transaction)
        .where(Transaction.id == transaction_id, Transaction.workspace_id == workspace_id)
        .options(selectinload(Transaction.cost_center_allocations))
    )
    tx = result.scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=404, detail="transaction_not_found")
    return tx


async def _guard_period(session: AsyncSession, tx: Transaction) -> None:
    """Ratear muda o resultado por centro de custo: respeita o fechamento de período (A5)."""
    from app.services import period_close_service as pcs

    ws = await session.get(Workspace, tx.workspace_id)
    if ws and await pcs.is_period_closed(session, ws, tx.date, tx.effective_date):
        raise _err("period_closed", period=f"{tx.date.year}-{tx.date.month:02d}")


def _split_by_percentage(total: Decimal, pcts: list[Decimal]) -> list[Decimal]:
    amounts = [_cents(total * p / _HUNDRED) for p in pcts]
    amounts[-1] = total - sum(amounts[:-1], Decimal("0"))  # resíduo na última
    return amounts


async def get_allocations(
    session: AsyncSession, transaction_id: uuid.UUID, workspace_id: uuid.UUID
) -> list[CostCenterAllocation]:
    result = await session.execute(
        select(CostCenterAllocation)
        .where(
            CostCenterAllocation.transaction_id == transaction_id,
            CostCenterAllocation.workspace_id == workspace_id,
        )
        .order_by(CostCenterAllocation.created_at, CostCenterAllocation.id)
    )
    return list(result.scalars().all())


async def set_allocations(
    session: AsyncSession,
    transaction_id: uuid.UUID,
    workspace_id: uuid.UUID,
    allocations: list[dict],
) -> list[CostCenterAllocation]:
    """Substitui o rateio. Cada item traz `cost_center_id` e `percentage` OU `amount`."""
    tx = await _load_transaction(session, transaction_id, workspace_id)
    await _guard_period(session, tx)

    if not allocations:
        raise _err("allocations_empty")
    cc_ids = [a["cost_center_id"] for a in allocations]
    if len(set(cc_ids)) != len(cc_ids):
        raise _err("allocations_duplicate_cost_center")

    use_pct = [a.get("percentage") is not None for a in allocations]
    use_amt = [a.get("amount") is not None for a in allocations]
    if any(p == m for p, m in zip(use_pct, use_amt)):
        raise _err("allocation_needs_percentage_or_amount")  # exatamente um dos dois por item
    if any(use_pct) and any(use_amt):
        raise _err("allocations_mixed_modes")

    found = await session.execute(
        select(CostCenter.id).where(CostCenter.id.in_(cc_ids), CostCenter.workspace_id == workspace_id)
    )
    if len({row[0] for row in found.all()}) != len(cc_ids):
        raise HTTPException(status_code=404, detail="cost_center_not_found")

    total = tx.amount
    stored_pcts: list[Optional[Decimal]]
    if all(use_pct):
        pcts = [Decimal(str(a["percentage"])) for a in allocations]
        if any(p <= 0 for p in pcts):
            raise _err("allocation_must_be_positive")
        if abs(sum(pcts) - _HUNDRED) > _PCT_TOLERANCE:
            raise _err("allocations_percentage_sum", expected="100", got=str(sum(pcts)))
        amounts = _split_by_percentage(total, pcts)
        stored_pcts = [p.quantize(_PCT) for p in pcts]
    else:
        amounts = [_cents(Decimal(str(a["amount"]))) for a in allocations]
        if any(a <= 0 for a in amounts):
            raise _err("allocation_must_be_positive")
        if sum(amounts) != total:
            raise _err("allocations_amount_sum", expected=str(total), got=str(sum(amounts)))
        stored_pcts = [(a / total * _HUNDRED).quantize(_PCT) if total else None for a in amounts]

    if any(a <= 0 for a in amounts):  # percentual minúsculo que arredondou para zero
        raise _err("allocation_must_be_positive")

    await session.execute(
        delete(CostCenterAllocation).where(CostCenterAllocation.transaction_id == tx.id)
    )
    session.expire(tx, ["cost_center_allocations"])
    session.add_all(
        CostCenterAllocation(
            workspace_id=workspace_id,
            transaction_id=tx.id,
            cost_center_id=cc_id,
            amount=amt,
            percentage=pct,
        )
        for cc_id, amt, pct in zip(cc_ids, amounts, stored_pcts)
    )
    tx.cost_center_id = max(zip(amounts, cc_ids), key=lambda pair: pair[0])[1]
    await session.commit()
    return await get_allocations(session, tx.id, workspace_id)


async def clear_allocations(
    session: AsyncSession, transaction_id: uuid.UUID, workspace_id: uuid.UUID
) -> None:
    """Remove o rateio. `cost_center_id` permanece no centro de maior fatia (o principal)."""
    tx = await _load_transaction(session, transaction_id, workspace_id)
    await _guard_period(session, tx)
    await session.execute(
        delete(CostCenterAllocation).where(CostCenterAllocation.transaction_id == tx.id)
    )
    session.expire(tx, ["cost_center_allocations"])
    await session.commit()


async def rescale_allocations(session: AsyncSession, tx: Transaction) -> None:
    """Mantém a invariante quando o valor da transação muda: refaz as fatias pelos percentuais."""
    allocations = list(tx.cost_center_allocations)
    if not allocations:
        return
    old_total = sum((a.amount for a in allocations), Decimal("0"))
    if old_total == 0:
        return
    pcts = [a.amount / old_total * _HUNDRED for a in allocations]
    for alloc, amt, pct in zip(allocations, _split_by_percentage(tx.amount, pcts), pcts):
        alloc.amount = amt
        alloc.percentage = pct.quantize(_PCT)
