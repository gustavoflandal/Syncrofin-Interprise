"""Accepting the suggestions the engine is confident about.

The queue exists because matching is sometimes unsure. But unsure is a
spectrum: a payment for exactly the invoice amount, from the right
counterparty, two days after the due date, with a description that reads the
same, is a question nobody has ever answered "no" to. Making a person click
through a hundred of those is how the queue becomes something they clear
without reading, and then the one that mattered goes through unread.

So a workspace can set a bar (`reconciliation_auto_apply_score`) and the
system takes what clears it. The rules for "clears it" are deliberately
stricter than the score alone:

    - the description score is at least the workspace's bar
    - the amount is *exactly* what was expected (a near miss is a human's call)
    - the payment is within `MAX_DAYS_APART` of the expected date
    - it is a question of one (a payment offered against several invoices is
      "does this cover these three?", and is never answered by a threshold)

Everything auto-accepted is written to the reconciliation history with no
user on it and `detail.auto_applied = true`. That is the audit trail, and it
is what lets anyone answer "did a person do this, or the rules?", and undo
it the ordinary way (unlink).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reconciliation import ReconciliationSuggestion
from app.services import (
    invoice_service,
    reconciliation_history_service,
    reconciliation_settle_service,
    reconciliation_suggestion_service as suggestions,
)

logger = logging.getLogger(__name__)

MAX_DAYS_APART = 7
#: Never go below this, whatever a workspace asks: under half, the "match" is a coin flip.
MIN_ALLOWED_SCORE = Decimal("0.5")


@dataclass
class AutoApplyResult:
    applied: int = 0
    skipped: int = 0
    failed: int = 0


def is_eligible(row: ReconciliationSuggestion, min_score: float) -> bool:
    """Whether one suggestion clears the bar. Pure, so it is tested alone."""
    if row.status != "pending" or row.group_id is not None:
        return False
    # Several deposits adding up to an invoice is never answered by a threshold.
    if row.is_aggregate:
        return False
    scores = row.scores or {}
    if int(scores.get("of_set", 1) or 1) != 1:
        return False
    if not scores.get("amount_exact"):
        return False
    if abs(int(scores.get("days_apart", 10**6))) > MAX_DAYS_APART:
        return False
    try:
        return float(scores.get("description", 0)) >= min_score
    except (TypeError, ValueError):
        return False


async def auto_apply(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    min_score: Optional[Decimal | float],
) -> AutoApplyResult:
    """Accept every eligible pending suggestion in the workspace. Commits nothing.

    Each one runs in its own savepoint: one that refuses (the invoice was
    voided a minute ago) is left pending for a person, and does not undo the
    ones that went through.
    """
    result = AutoApplyResult()
    if min_score is None:
        return result
    bar = max(float(min_score), float(MIN_ALLOWED_SCORE))

    for row in await suggestions.open_for(session, workspace_id, limit=500):
        if not is_eligible(row, bar):
            result.skipped += 1
            continue
        try:
            async with session.begin_nested():
                await reconciliation_settle_service.settle_member(session, workspace_id, row)
                await suggestions.mark_accepted(session, row, None)
                await reconciliation_history_service.record(
                    session,
                    workspace_id,
                    "accepted",
                    expectation_kind=row.expectation_kind,
                    expectation_id=row.expectation_id,
                    amount=row.amount,
                    transaction_id=row.transaction_id,
                    strategy_id=row.strategy_id,
                    user_id=None,
                    detail={
                        "auto_applied": True,
                        "score": (row.scores or {}).get("description"),
                        "threshold": bar,
                    },
                )
            result.applied += 1
        except invoice_service.InvoiceError as exc:
            logger.info("Auto-apply left suggestion %s pending: %s", row.id, exc)
            result.failed += 1
    return result
