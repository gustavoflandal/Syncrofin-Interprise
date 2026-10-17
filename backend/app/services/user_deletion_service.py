"""The cascade a person's data goes through when their account is deleted — shared by the admin's
'Delete user' action and the self-service erasure request (D1). Business rules about *whether* a
deletion may proceed (last superuser standing, sole owner of a shared workspace) belong to the caller;
this module only does the deleting, faithfully, for both callers.
"""
import uuid

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.asset import Asset
from app.models.asset_group import AssetGroup
from app.models.asset_value import AssetValue
from app.models.bank_connection import BankConnection
from app.models.budget import Budget
from app.models.category import Category
from app.models.category_group import CategoryGroup
from app.models.collection import Collection
from app.models.credit_card_bill import CreditCardBill
from app.models.goal import Goal
from app.models.import_log import ImportLog
from app.models.invoice import Invoice
from app.models.invoice_attachment import InvoiceAttachment
from app.models.payee import Payee, PayeeMapping
from app.models.reconciliation import ReconciliationEvent, ReconciliationRule, ReconciliationSuggestion
from app.models.recurring_transaction import RecurringTransaction
from app.models.rule import Rule
from app.models.transaction import Transaction
from app.models.transaction_attachment import TransactionAttachment
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember


async def _delete_owned_data(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Every financial entity keyed directly by `user_id`, in dependency order. Faithful copy of what
    `admin_service.delete_user` did inline before this module existed — do not reorder without checking
    which tables reference which (attachments before transactions, asset values before assets)."""
    tx_ids_query = select(Transaction.id).where(Transaction.user_id == user_id)
    await session.execute(delete(TransactionAttachment).where(TransactionAttachment.transaction_id.in_(tx_ids_query)))
    # An attachment this person uploaded onto SOMEONE ELSE's transaction isn't caught by the
    # transaction_id pass above (that transaction isn't theirs) but still carries their own `user_id`
    # FK — deleting it here is what keeps that FK from 500ing the erasure.
    await session.execute(delete(TransactionAttachment).where(TransactionAttachment.user_id == user_id))
    await session.execute(delete(Transaction).where(Transaction.user_id == user_id))
    await session.execute(delete(Budget).where(Budget.user_id == user_id))
    await session.execute(delete(RecurringTransaction).where(RecurringTransaction.user_id == user_id))
    await session.execute(delete(ImportLog).where(ImportLog.user_id == user_id))
    await session.execute(delete(Rule).where(Rule.user_id == user_id))

    # Goal must be deleted before Asset: `Goal.asset_id -> assets.id` carries NO `ondelete` action
    # (defaults to RESTRICT/NO ACTION at the database level), so a Goal still pointing at an Asset
    # would block that Asset's delete below with a ForeignKeyViolation. `Goal.account_id` and
    # `Goal.asset_group_id` are both `ondelete="SET NULL"`, so Goal's order relative to Account and
    # AssetGroup is unconstrained — only the Asset edge is a hard dependency.
    await session.execute(delete(Goal).where(Goal.user_id == user_id))

    asset_ids_query = select(Asset.id).where(Asset.user_id == user_id)
    await session.execute(delete(AssetValue).where(AssetValue.asset_id.in_(asset_ids_query)))
    await session.execute(delete(Asset).where(Asset.user_id == user_id))
    await session.execute(delete(AssetGroup).where(AssetGroup.user_id == user_id))

    # An invoice attachment this person uploaded onto SOMEONE ELSE's invoice, same reasoning as
    # TransactionAttachment above — must go before the Invoice delete below only so both passes read
    # cleanly together; the two WHERE clauses don't actually overlap in a way that requires ordering.
    await session.execute(delete(InvoiceAttachment).where(InvoiceAttachment.user_id == user_id))
    # Invoice must be deleted before Payee/PayeeMapping below: `Invoice.payee_id -> payees.id` is
    # `ondelete="RESTRICT"` DELIBERATELY (see invoice.py's own docstring — deleting a client must never
    # silently delete the record of money they owed), so a still-existing Invoice referencing a Payee
    # would block that Payee's delete. InvoiceLine, InvoiceAllocation and InvoiceAttachment all carry
    # `ondelete="CASCADE"` on their invoice_id FK, so the database removes them the moment the Invoice
    # row goes — no separate pass needed here for the person's own invoices.
    #
    # (InvoiceAllocation.transaction_id is also `ondelete="CASCADE"` from transactions.id, but that's
    # irrelevant to this ordering: Transaction is already deleted above, which would have cascaded away
    # any allocation pointing at it before we ever reach this line — and any allocation still standing
    # here is removed automatically the moment its Invoice goes, regardless of Transaction's fate.)
    await session.execute(delete(Invoice).where(Invoice.user_id == user_id))

    await session.execute(delete(PayeeMapping).where(PayeeMapping.user_id == user_id))
    await session.execute(delete(Payee).where(Payee.user_id == user_id))
    await session.execute(delete(Account).where(Account.user_id == user_id))
    await session.execute(delete(Category).where(Category.user_id == user_id))
    await session.execute(delete(CategoryGroup).where(CategoryGroup.user_id == user_id))
    await session.execute(delete(BankConnection).where(BankConnection.user_id == user_id))
    await session.execute(delete(Collection).where(Collection.user_id == user_id))
    await session.execute(delete(CreditCardBill).where(CreditCardBill.user_id == user_id))

    # `reconciliation_rules.user_id`, `reconciliation_suggestions.resolved_by` and
    # `reconciliation_events.user_id` are attribution ("who changed this" / "who resolved this"),
    # never ownership — the row is a workspace-wide rule override or an audit-shaped history entry
    # that other members still need after this person is gone. They're nullable exactly so this is
    # possible; only the `ondelete` action to make it automatic was missing from the migration. Null
    # the actor out instead of deleting the row, mirroring what `Workspace.created_by_user_id` already
    # does at the database level.
    await session.execute(update(ReconciliationRule).where(ReconciliationRule.user_id == user_id).values(user_id=None))
    await session.execute(
        update(ReconciliationSuggestion)
        .where(ReconciliationSuggestion.resolved_by == user_id)
        .values(resolved_by=None)
    )
    await session.execute(update(ReconciliationEvent).where(ReconciliationEvent.user_id == user_id).values(user_id=None))


async def _workspace_ids_of(session: AsyncSession, user_id: uuid.UUID) -> list[uuid.UUID]:
    result = await session.execute(select(WorkspaceMember.workspace_id).where(WorkspaceMember.user_id == user_id))
    return [row for row in result.scalars().all()]


async def _delete_orphaned_workspaces(session: AsyncSession, workspace_ids: list[uuid.UUID]) -> None:
    """A workspace whose last member just left (their `workspace_members` row cascades away with the
    user, at the database level, before this runs) is unreachable forever — nobody can be added to a
    workspace they cannot see. Deleting it here is a cleanup the admin cascade never did; see the D1
    plan's Task 2 for why it's added now rather than left as a pre-existing gap."""
    if not workspace_ids:
        return
    still_has_members = (
        await session.execute(
            select(WorkspaceMember.workspace_id).where(WorkspaceMember.workspace_id.in_(workspace_ids)).distinct()
        )
    ).scalars().all()
    orphaned = set(workspace_ids) - set(still_has_members)
    if orphaned:
        await session.execute(delete(Workspace).where(Workspace.id.in_(orphaned)))


async def delete_user_data(session: AsyncSession, user: User) -> None:
    """Delete `user`'s owned financial data, the user row itself, and any workspace left with no
    members. Does not commit — the caller commits, after any of its own last write (e.g. sending a
    confirmation e-mail while `user.email` is still readable)."""
    workspace_ids = await _workspace_ids_of(session, user.id)
    await _delete_owned_data(session, user.id)
    await session.delete(user)
    await session.flush()  # so the `workspace_members` cascade from the FK has actually happened
    await _delete_orphaned_workspaces(session, workspace_ids)
