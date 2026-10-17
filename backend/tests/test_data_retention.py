"""D2: data retention policy tests."""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.data_retention import DataRetentionPolicy
from app.models.transaction import Transaction
from app.models.workspace import Workspace, WorkspaceMember
from app.models.user import User
from app.services import data_retention_service


@pytest_asyncio.fixture
async def workspace_with_user(session: AsyncSession):
    """Create a user, workspace, and membership for tests."""
    user = User(
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="fake",
    )
    session.add(user)
    await session.flush()

    ws = Workspace(name="Test WS", created_by_user_id=user.id)
    session.add(ws)
    await session.flush()

    member = WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner")
    session.add(member)
    await session.flush()

    account = Account(
        user_id=user.id,
        workspace_id=ws.id,
        name="Test Account",
        type="checking",
        currency="BRL",
        balance=Decimal("0"),
    )
    session.add(account)
    await session.flush()

    return user, ws, account


@pytest.mark.asyncio
async def test_default_policy_created(session: AsyncSession, workspace_with_user):
    """Getting a policy for a workspace with none should create defaults."""
    _, ws, _ = workspace_with_user
    policy = await data_retention_service.get_policy(session, ws.id)
    assert policy is not None
    assert policy.workspace_id == ws.id
    assert policy.transaction_retention_days == 2555
    assert policy.attachment_retention_days == 1825
    assert policy.audit_retention_days == 3650
    assert policy.anonymize_on_expiry is True


@pytest.mark.asyncio
async def test_update_policy(session: AsyncSession, workspace_with_user):
    """Updating retention days should persist the change."""
    _, ws, _ = workspace_with_user
    updated = await data_retention_service.update_policy(
        session, ws.id, {"transaction_retention_days": 730, "anonymize_on_expiry": False}
    )
    assert updated.transaction_retention_days == 730
    assert updated.anonymize_on_expiry is False

    # Fetch again to confirm
    fetched = await data_retention_service.get_policy(session, ws.id)
    assert fetched.transaction_retention_days == 730


@pytest.mark.asyncio
async def test_min_retention_enforced(session: AsyncSession, workspace_with_user):
    """Setting retention below 365 should be rejected by the DB CHECK constraint."""
    from sqlalchemy.exc import IntegrityError

    _, ws, _ = workspace_with_user
    policy = await data_retention_service.get_policy(session, ws.id)
    policy.transaction_retention_days = 100
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


@pytest.mark.asyncio
async def test_purge_anonymizes_old_transactions(session: AsyncSession, workspace_with_user):
    """Transactions older than the retention period should be anonymized."""
    user, ws, account = workspace_with_user

    # Create a policy with a short retention for testing
    policy = DataRetentionPolicy(
        workspace_id=ws.id,
        transaction_retention_days=365,
        attachment_retention_days=365,
        audit_retention_days=365,
    )
    session.add(policy)
    await session.flush()

    # Create an old transaction (2 years ago)
    old_tx = Transaction(
        user_id=user.id,
        workspace_id=ws.id,
        account_id=account.id,
        description="Old payment to supplier",
        amount=Decimal("100.00"),
        currency="BRL",
        date=date.today() - timedelta(days=800),
        effective_date=date.today() - timedelta(days=800),
        type="debit",
        source="manual",
        payee="Supplier Inc",
        notes="Some notes",
    )
    session.add(old_tx)
    await session.flush()
    old_tx_id = old_tx.id

    session.expunge_all()

    counts = await data_retention_service.purge_expired_data(session, ws.id)
    assert counts["transactions_anonymized"] == 1

    # Verify the transaction was anonymized
    result = await session.execute(select(Transaction).where(Transaction.id == old_tx_id))
    tx = result.scalar_one()
    assert tx.description == "[anonimizado]"
    assert tx.notes is None
    assert tx.payee is None
    assert tx.payee_id is None
    # Amount and date preserved for accounting
    assert tx.amount == Decimal("100.00")
    assert tx.date == date.today() - timedelta(days=800)


@pytest.mark.asyncio
async def test_purge_skips_recent(session: AsyncSession, workspace_with_user):
    """Recent transactions should not be touched by purge."""
    user, ws, account = workspace_with_user

    policy = DataRetentionPolicy(
        workspace_id=ws.id,
        transaction_retention_days=365,
        attachment_retention_days=365,
        audit_retention_days=365,
    )
    session.add(policy)
    await session.flush()

    # Create a recent transaction
    recent_tx = Transaction(
        user_id=user.id,
        workspace_id=ws.id,
        account_id=account.id,
        description="Recent payment",
        amount=Decimal("50.00"),
        currency="BRL",
        date=date.today() - timedelta(days=30),
        effective_date=date.today() - timedelta(days=30),
        type="debit",
        source="manual",
        notes="Recent notes",
    )
    session.add(recent_tx)
    await session.flush()
    recent_tx_id = recent_tx.id

    session.expunge_all()

    counts = await data_retention_service.purge_expired_data(session, ws.id)
    assert counts["transactions_anonymized"] == 0

    # Verify the transaction is untouched
    result = await session.execute(select(Transaction).where(Transaction.id == recent_tx_id))
    tx = result.scalar_one()
    assert tx.description == "Recent payment"
    assert tx.notes == "Recent notes"
