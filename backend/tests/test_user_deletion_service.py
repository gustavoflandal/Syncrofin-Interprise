"""The cascade shared by admin deletion and self-service erasure: owned data, the user, and any
workspace that becomes memberless as a result."""
import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.asset import Asset
from app.models.asset_group import AssetGroup
from app.models.collection import Collection
from app.models.credit_card_bill import CreditCardBill
from app.models.goal import Goal
from app.models.invoice import Invoice, InvoiceLine
from app.models.invoice_attachment import InvoiceAttachment
from app.models.payee import Payee
from app.models.reconciliation import ReconciliationEvent, ReconciliationRule, ReconciliationSuggestion
from app.models.transaction import Transaction
from app.models.transaction_attachment import TransactionAttachment
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import user_deletion_service

pytestmark = pytest.mark.asyncio


class TestDeleteUserData:
    async def test_it_deletes_the_user_and_their_owned_data(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        account = Account(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
            name="Conta", type="checking", balance=0, currency="BRL",
        )
        session.add(account)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        assert (await session.execute(select(User).where(User.id == test_user.id))).scalar_one_or_none() is None
        assert (await session.execute(select(Account).where(Account.id == account.id))).scalar_one_or_none() is None

    async def test_it_removes_a_workspace_that_becomes_memberless(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        """test_user is the workspace's only member (see the `test_user` fixture): once they're gone,
        nobody can ever see this workspace again, so it should not linger as an orphan."""
        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        remaining = (await session.execute(select(Workspace).where(Workspace.id == test_workspace.id))).scalar_one_or_none()
        assert remaining is None

    async def test_it_keeps_a_workspace_that_still_has_other_members(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        other = User(
            id=uuid.uuid4(), email="other@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add(other)
        await session.flush()
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=other.id, role="editor"))
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        remaining = (await session.execute(select(Workspace).where(Workspace.id == test_workspace.id))).scalar_one_or_none()
        assert remaining is not None


class TestNoOndeleteTablesDontFkViolate:
    """Second-round re-review: `Goal`, `Collection`, `CreditCardBill`, `AssetGroup` and `Invoice` all
    have a `user_id` FK to `users.id` with NO `ondelete` action at all, and weren't in
    `_delete_owned_data` — so deleting their owner used to raise a `ForeignKeyViolation`. One test per
    table proves the row is gone and no exception is raised."""

    async def test_it_deletes_a_goal(self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db):
        goal = Goal(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
            name="Reserva de emergência", target_amount="1000.00",
        )
        session.add(goal)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        assert (await session.execute(select(Goal).where(Goal.id == goal.id))).scalar_one_or_none() is None

    async def test_it_deletes_a_collection(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        collection = Collection(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id, name="Contas do dia a dia",
        )
        session.add(collection)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        assert (
            await session.execute(select(Collection).where(Collection.id == collection.id))
        ).scalar_one_or_none() is None

    async def test_it_deletes_a_credit_card_bill(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        account = Account(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
            name="Cartão", type="credit_card", currency="BRL",
        )
        session.add(account)
        await session.flush()
        bill = CreditCardBill(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id, account_id=account.id,
            external_id="bill-1", due_date=date.today(), total_amount="500.00",
        )
        session.add(bill)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        assert (
            await session.execute(select(CreditCardBill).where(CreditCardBill.id == bill.id))
        ).scalar_one_or_none() is None

    async def test_it_deletes_an_asset_group(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        group = AssetGroup(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id, name="US Stocks",
        )
        session.add(group)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        assert (
            await session.execute(select(AssetGroup).where(AssetGroup.id == group.id))
        ).scalar_one_or_none() is None

    async def test_it_deletes_an_invoice_and_its_lines_and_allocations(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        """`InvoiceLine` and `InvoiceAllocation` both carry `ondelete="CASCADE"` on `invoice_id`, so
        they're expected to disappear with the invoice via the database, not via any explicit delete."""
        invoice = Invoice(
            id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=test_user.id,
            issue_date=date.today(), due_date=date.today(),
        )
        session.add(invoice)
        await session.flush()
        line = InvoiceLine(
            id=uuid.uuid4(), invoice_id=invoice.id, workspace_id=test_workspace.id,
            description="Consultoria", unit_price="100.00", total="100.00",
        )
        session.add(line)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        assert (await session.execute(select(Invoice).where(Invoice.id == invoice.id))).scalar_one_or_none() is None
        assert (
            await session.execute(select(InvoiceLine).where(InvoiceLine.id == line.id))
        ).scalar_one_or_none() is None


class TestThirdRoundDeleteOrderFixes:
    """Third-round review: FKs that used to break the erasure cascade because of delete ORDER rather
    than a missing `ondelete`. The existing `Goal`/`Invoice` tests above pass with `asset_id`/
    `payee_id` left `None`, which is exactly why this gap wasn't caught earlier — these tests set the
    FK to a real row the same person owns."""

    async def test_it_deletes_a_goal_that_tracks_an_asset(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        """`Goal.asset_id -> assets.id` has no `ondelete` (defaults to RESTRICT/NO ACTION), so deleting
        Asset before Goal used to raise a `ForeignKeyViolation` whenever a goal tracked an asset."""
        asset = Asset(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
            name="Tesouro Selic", type="investment", currency="BRL",
        )
        session.add(asset)
        await session.flush()
        goal = Goal(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id,
            name="Reserva via Tesouro", target_amount="1000.00",
            tracking_type="asset", asset_id=asset.id,
        )
        session.add(goal)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        assert (await session.execute(select(Goal).where(Goal.id == goal.id))).scalar_one_or_none() is None
        assert (await session.execute(select(Asset).where(Asset.id == asset.id))).scalar_one_or_none() is None

    async def test_it_deletes_an_invoice_with_a_payee(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        """`Invoice.payee_id -> payees.id` is `ondelete="RESTRICT"` DELIBERATELY (see invoice.py) — the
        fix is delete ORDER (Invoice before Payee), not the RESTRICT itself. Before the fix, deleting
        Payee first used to raise a `ForeignKeyViolation` whenever an invoice named a payee."""
        payee = Payee(
            id=uuid.uuid4(), user_id=test_user.id, workspace_id=test_workspace.id, name="Cliente Exemplo",
        )
        session.add(payee)
        await session.flush()
        invoice = Invoice(
            id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=test_user.id, payee_id=payee.id,
            issue_date=date.today(), due_date=date.today(),
        )
        session.add(invoice)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        assert (await session.execute(select(Invoice).where(Invoice.id == invoice.id))).scalar_one_or_none() is None
        assert (await session.execute(select(Payee).where(Payee.id == payee.id))).scalar_one_or_none() is None


class TestOwnUserIdAttachmentsOnSomeoneElsesRow:
    """`TransactionAttachment` and `InvoiceAttachment` are usually deleted by their PARENT's id (the
    person's own transaction/invoice), but each also carries its own `user_id` — the uploader. An
    attachment this person uploaded onto SOMEONE ELSE's transaction/invoice isn't reached by the
    parent-id pass and used to 500 the erasure via that column."""

    async def test_it_deletes_a_transaction_attachment_uploaded_onto_someone_elses_transaction(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        other = User(
            id=uuid.uuid4(), email="attach-owner@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add(other)
        await session.flush()
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=other.id, role="editor"))
        account = Account(
            id=uuid.uuid4(), user_id=other.id, workspace_id=test_workspace.id,
            name="Conta do outro", type="checking", currency="BRL",
        )
        session.add(account)
        await session.flush()
        tx = Transaction(
            id=uuid.uuid4(), user_id=other.id, workspace_id=test_workspace.id, account_id=account.id,
            description="Transação do outro", amount="10.00", date=date.today(), type="debit", source="manual",
        )
        session.add(tx)
        await session.flush()
        attachment = TransactionAttachment(
            id=uuid.uuid4(), transaction_id=tx.id, user_id=test_user.id, workspace_id=test_workspace.id,
            filename="recibo.pdf", storage_key="k1", content_type="application/pdf", size=100,
        )
        session.add(attachment)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        assert (
            await session.execute(select(TransactionAttachment).where(TransactionAttachment.id == attachment.id))
        ).scalar_one_or_none() is None
        # The other person's transaction is untouched — only the attachment this person uploaded is gone.
        assert (await session.execute(select(Transaction).where(Transaction.id == tx.id))).scalar_one_or_none() is not None

    async def test_it_deletes_an_invoice_attachment_uploaded_onto_someone_elses_invoice(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        other = User(
            id=uuid.uuid4(), email="invoice-owner@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add(other)
        await session.flush()
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=other.id, role="editor"))
        invoice = Invoice(
            id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=other.id,
            issue_date=date.today(), due_date=date.today(),
        )
        session.add(invoice)
        await session.flush()
        attachment = InvoiceAttachment(
            id=uuid.uuid4(), invoice_id=invoice.id, workspace_id=test_workspace.id, user_id=test_user.id,
            filename="nota.pdf", storage_key="k2", content_type="application/pdf", size=200,
        )
        session.add(attachment)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        assert (
            await session.execute(select(InvoiceAttachment).where(InvoiceAttachment.id == attachment.id))
        ).scalar_one_or_none() is None
        # The other person's invoice is untouched — only the attachment this person uploaded is gone.
        assert (
            await session.execute(select(Invoice).where(Invoice.id == invoice.id))
        ).scalar_one_or_none() is not None


class TestReconciliationAttributionIsNulledNotDeleted:
    """`reconciliation_rules.user_id`, `reconciliation_suggestions.resolved_by` and
    `reconciliation_events.user_id` are attribution, not ownership — a workspace rule override or an
    audit-shaped history entry that other members still need. They're nullable with no `ondelete`, so
    deleting their author used to 500; the fix nulls the actor out and keeps the row."""

    async def test_it_nulls_a_reconciliation_rule_authored_by_the_person(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        # A second member keeps test_workspace from being deleted as orphaned once test_user is gone —
        # otherwise the workspace's own CASCADE would take the rule with it, and the test would prove
        # nothing about the nulling behaviour this test exists to check.
        other = User(
            id=uuid.uuid4(), email="rule-other@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add(other)
        await session.flush()
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=other.id, role="editor"))
        rule = ReconciliationRule(
            id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=test_user.id,
            node="invoices", strategy_id="exact_amount_date",
        )
        session.add(rule)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        await session.refresh(rule)
        assert rule.user_id is None

    async def test_it_nulls_a_reconciliation_suggestion_resolved_by_the_person(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        # Same reasoning as above for the workspace, plus: the transaction the suggestion points at
        # belongs to `other`, not `test_user` — if it were test_user's own transaction, deleting that
        # transaction (an owned-data pass) would CASCADE-delete the suggestion outright, which is
        # correct behaviour but not what this test is checking (the resolved_by nulling).
        other = User(
            id=uuid.uuid4(), email="suggestion-other@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add(other)
        await session.flush()
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=other.id, role="editor"))
        account = Account(
            id=uuid.uuid4(), user_id=other.id, workspace_id=test_workspace.id,
            name="Conta", type="checking", currency="BRL",
        )
        session.add(account)
        await session.flush()
        tx = Transaction(
            id=uuid.uuid4(), user_id=other.id, workspace_id=test_workspace.id, account_id=account.id,
            description="Pagamento", amount="50.00", date=date.today(), type="debit", source="manual",
        )
        session.add(tx)
        await session.flush()
        suggestion = ReconciliationSuggestion(
            id=uuid.uuid4(), workspace_id=test_workspace.id, transaction_id=tx.id,
            expectation_kind="invoice", expectation_id=uuid.uuid4(), strategy_id="exact_amount_date",
            node="invoices", amount="50.00", resolved_by=test_user.id,
        )
        session.add(suggestion)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        await session.refresh(suggestion)
        assert suggestion.resolved_by is None

    async def test_it_nulls_a_reconciliation_event_actor(
        self, session: AsyncSession, test_user: User, test_workspace: Workspace, clean_db
    ):
        other = User(
            id=uuid.uuid4(), email="event-other@example.com", hashed_password="x",
            is_active=True, is_superuser=False, is_verified=True,
        )
        session.add(other)
        await session.flush()
        session.add(WorkspaceMember(id=uuid.uuid4(), workspace_id=test_workspace.id, user_id=other.id, role="editor"))
        event = ReconciliationEvent(
            id=uuid.uuid4(), workspace_id=test_workspace.id, action="linked",
            expectation_kind="invoice", expectation_id=uuid.uuid4(), amount="50.00", user_id=test_user.id,
        )
        session.add(event)
        await session.commit()

        await user_deletion_service.delete_user_data(session, test_user)
        await session.commit()

        await session.refresh(event)
        assert event.user_id is None
