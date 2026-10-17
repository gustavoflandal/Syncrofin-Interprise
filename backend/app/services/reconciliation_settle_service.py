"""Writing one accepted suggestion, whoever accepted it.

Extracted from the accept route so the person clicking "accept" and the
system accepting a confident match take the *same* write path. Two copies
of "what accepting means" would drift, and the drift would show up as an
automatic match that leaves the ledger different from a manual one.

Marking the suggestion and recording history stay with the callers: the
route does them for a person, `reconciliation_auto_service` for the system.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, InvoiceAllocation
from app.models.reconciliation import ReconciliationSuggestion
from app.models.recurring_transaction import RecurringTransaction
from app.services import invoice_service


async def settle_member(
    session: AsyncSession, workspace_id: uuid.UUID, row: ReconciliationSuggestion
) -> None:
    """Write one member of an accepted question.

    An invoice gets an allocation; a recurring bill gets the charge bound to
    it. Raises `invoice_service.InvoiceError` when what it points at is gone
    or refuses the payment.
    """
    if row.expectation_kind == "invoice" and row.is_aggregate:
        await _settle_aggregate(session, workspace_id, row)
        return

    if row.expectation_kind == "invoice":
        invoice = await session.get(Invoice, row.expectation_id)
        if invoice is None or invoice.workspace_id != workspace_id:
            raise invoice_service.InvoiceError("invoice_missing", "The invoice is no longer there")
        await invoice_service.allocate(
            session,
            invoice,
            row.transaction_id,
            amount=row.amount,
            # The rule that suggested it, not "manual": the match is credited
            # to a specific rule, and that is worth keeping.
            method=row.strategy_id,
        )
        return

    bill = await session.get(RecurringTransaction, row.expectation_id)
    if bill is None or bill.workspace_id != workspace_id:
        raise invoice_service.InvoiceError("bill_missing", "The recurring bill is no longer there")
    from app.services import recurring_match_service

    transaction = row.transaction
    transaction.recurring_transaction_id = bill.id
    recurring_match_service.advance_past(bill, transaction.date)


async def _settle_aggregate(
    session: AsyncSession, workspace_id: uuid.UUID, row: ReconciliationSuggestion
) -> None:
    """N deposits against one invoice: one allocation per deposit.

    Each deposit is allocated for what it carried, capped by what the
    invoice still owes, so a group inside the rule's tolerance never writes
    more than the invoice is worth (`allocate` would refuse it anyway).
    A deposit that already settles something refuses the whole group: it
    was one question, and settling part of it would leave the invoice
    short with nothing having said so.
    """
    invoice = await session.get(Invoice, row.expectation_id)
    if invoice is None or invoice.workspace_id != workspace_id:
        raise invoice_service.InvoiceError("invoice_missing", "The invoice is no longer there")

    deposits = [m.transaction for m in row.member_transactions]
    for tx in deposits:
        taken = await session.execute(
            select(InvoiceAllocation.id).where(InvoiceAllocation.transaction_id == tx.id).limit(1)
        )
        if taken.scalar_one_or_none() is not None:
            raise invoice_service.InvoiceError(
                "already_allocated", "One of these payments is already linked to an invoice"
            )

    for tx in sorted(deposits, key=lambda t: (t.date, str(t.id))):
        available = invoice_service.balance(invoice)
        if available <= 0:
            break
        await invoice_service.allocate(
            session,
            invoice,
            tx.id,
            amount=min(abs(tx.amount), available),
            method=row.strategy_id,
        )

    # The deposits are spoken for now: retire the 1:1 questions they raised.
    from app.services import reconciliation_suggestion_service

    await reconciliation_suggestion_service.supersede_for_transactions(
        session, workspace_id, [tx.id for tx in deposits], keep=row.id
    )
