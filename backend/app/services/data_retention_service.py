"""D2: data retention and disposal.

Provides configurable retention policies per workspace and a purge function
that anonymizes or removes expired data, preserving accounting totals.
"""
import logging
import uuid
from datetime import datetime, date, timezone, timedelta

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_retention import DataRetentionPolicy
from app.models.transaction import Transaction
from app.models.transaction_attachment import TransactionAttachment
from app.models.invoice_attachment import InvoiceAttachment
from app.providers import get_storage_provider

logger = logging.getLogger(__name__)

# Default retention periods (days)
DEFAULT_TRANSACTION_DAYS = 2555  # ~7 years (Brazilian fiscal)
DEFAULT_ATTACHMENT_DAYS = 1825   # ~5 years
DEFAULT_AUDIT_DAYS = 3650        # ~10 years


async def get_policy(session: AsyncSession, workspace_id: uuid.UUID) -> DataRetentionPolicy:
    """Get or create the default retention policy for a workspace."""
    result = await session.execute(
        select(DataRetentionPolicy).where(DataRetentionPolicy.workspace_id == workspace_id)
    )
    policy = result.scalar_one_or_none()
    if policy is not None:
        return policy

    policy = DataRetentionPolicy(workspace_id=workspace_id)
    session.add(policy)
    await session.flush()
    return policy


async def update_policy(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    data: dict,
) -> DataRetentionPolicy:
    """Update the retention policy for a workspace."""
    policy = await get_policy(session, workspace_id)
    for key, value in data.items():
        if value is not None:
            setattr(policy, key, value)
    policy.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return policy


async def purge_expired_data(
    session: AsyncSession,
    workspace_id: uuid.UUID,
) -> dict:
    """Run data retention purge for one workspace.

    Returns counts of what was processed.
    """
    policy = await get_policy(session, workspace_id)
    today = date.today()

    # --- Transactions ---
    tx_cutoff = today - timedelta(days=policy.transaction_retention_days)
    tx_count = 0

    if policy.anonymize_on_expiry:
        # Anonymize: clear description, notes, payee info but keep amount/date/category
        result = await session.execute(
            update(Transaction)
            .where(
                Transaction.workspace_id == workspace_id,
                Transaction.date < tx_cutoff,
                Transaction.description != "[anonimizado]",
            )
            .values(
                description="[anonimizado]",
                original_description=None,
                notes=None,
                payee=None,
                payee_id=None,
            )
            .execution_options(synchronize_session=False)
        )
        tx_count = result.rowcount
    else:
        # Hard-delete old transactions (cascade will remove splits, attachments)
        # First clean up attachment files
        old_tx_ids_result = await session.execute(
            select(Transaction.id).where(
                Transaction.workspace_id == workspace_id,
                Transaction.date < tx_cutoff,
            )
        )
        old_tx_ids = [row[0] for row in old_tx_ids_result.all()]
        if old_tx_ids:
            from app.services.attachment_service import cleanup_attachment_files
            await cleanup_attachment_files(session, old_tx_ids)
            result = await session.execute(
                delete(Transaction).where(Transaction.id.in_(old_tx_ids))
            )
            tx_count = result.rowcount

    # --- Transaction Attachments (standalone, by age) ---
    att_cutoff = today - timedelta(days=policy.attachment_retention_days)
    att_cutoff_dt = datetime(att_cutoff.year, att_cutoff.month, att_cutoff.day, tzinfo=timezone.utc)

    # Transaction attachments older than the retention period
    old_tx_att_result = await session.execute(
        select(TransactionAttachment).where(
            TransactionAttachment.workspace_id == workspace_id,
            TransactionAttachment.created_at < att_cutoff_dt,
        )
    )
    old_tx_atts = old_tx_att_result.scalars().all()

    # Invoice attachments: only those whose retention_until has passed (or is None and old enough),
    # and not locked
    old_inv_att_result = await session.execute(
        select(InvoiceAttachment).where(
            InvoiceAttachment.workspace_id == workspace_id,
            InvoiceAttachment.created_at < att_cutoff_dt,
            InvoiceAttachment.is_locked == False,  # noqa: E712
            (InvoiceAttachment.retention_until.is_(None)) | (InvoiceAttachment.retention_until < today),
        )
    )
    old_inv_atts = old_inv_att_result.scalars().all()

    att_count = 0
    storage = get_storage_provider()
    for att in [*old_tx_atts, *old_inv_atts]:
        try:
            await storage.delete(att.storage_key)
        except Exception:
            pass  # best-effort
        await session.delete(att)
        att_count += 1

    # --- Audit events ---
    # Audit events are immutable by design (append-only with hash chain).
    # General audit events cannot be modified without breaking the chain.
    # Access-event anonymization is handled separately by the purge_access_log task.
    audit_count = 0

    # Update last_purge_at
    policy.last_purge_at = datetime.now(timezone.utc)
    await session.flush()

    logger.info(
        "Retention purge workspace=%s: transactions=%d attachments=%d audit=%d",
        workspace_id, tx_count, att_count, audit_count,
    )

    return {
        "transactions_anonymized": tx_count,
        "attachments_deleted": att_count,
        "audit_anonymized": audit_count,
    }
