"""Tests for document retention / attachment lock (B6)."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.models.invoice import Invoice
from app.models.invoice_attachment import InvoiceAttachment
from app.services.invoice_attachment_service import (
    AttachmentLockedError,
    delete,
    lock_attachment,
    update,
    upload,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_invoice(session, workspace_id, user_id):
    """Insert a minimal invoice the attachment can reference."""
    from decimal import Decimal
    import uuid

    inv = Invoice(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        user_id=user_id,
        direction="receivable",
        origin="local",
        status="open",
        currency="BRL",
        total=Decimal("100.00"),
        issue_date=date(2026, 1, 1),
        due_date=date(2026, 2, 1),
        number="T-001",
    )
    session.add(inv)
    return inv


async def _upload_attachment(session, workspace_id, user_id, invoice_id, **kwargs):
    """Upload a tiny test attachment through the service layer."""
    defaults = dict(
        filename="test.pdf",
        content_type="application/pdf",
        data=b"%PDF-1.4 test",
        kind="other",
    )
    defaults.update(kwargs)
    with patch("app.services.invoice_attachment_service.get_storage_provider") as mock_sp:
        from types import SimpleNamespace

        mock_storage = AsyncMock()
        mock_storage.upload.return_value = SimpleNamespace(
            storage_key=f"{workspace_id}/invoices/{invoice_id}/abc_{defaults['filename']}",
            content_type=defaults["content_type"],
            size=len(defaults["data"]),
        )
        mock_sp.return_value = mock_storage
        att = await upload(
            session=session,
            workspace_id=workspace_id,
            user_id=user_id,
            invoice_id=invoice_id,
            **defaults,
        )
    return att


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_locked_attachment_cannot_be_deleted(session, test_workspace, test_user):
    inv = _make_invoice(session, test_workspace.id, test_user.id)
    await session.flush()

    att = await _upload_attachment(session, test_workspace.id, test_user.id, inv.id)
    await lock_attachment(session, att, locked_by="user")

    assert att.is_locked is True

    with patch("app.services.invoice_attachment_service.get_storage_provider"):
        with pytest.raises(AttachmentLockedError):
            await delete(session, att.id, test_workspace.id)


@pytest.mark.asyncio
async def test_locked_attachment_cannot_be_modified(session, test_workspace, test_user):
    inv = _make_invoice(session, test_workspace.id, test_user.id)
    await session.flush()

    att = await _upload_attachment(session, test_workspace.id, test_user.id, inv.id)
    await lock_attachment(session, att, locked_by="system")

    with pytest.raises(AttachmentLockedError):
        await update(session, att.id, test_workspace.id, {"kind": "receipt"})


@pytest.mark.asyncio
async def test_locked_attachment_retention_can_be_extended(session, test_workspace, test_user):
    inv = _make_invoice(session, test_workspace.id, test_user.id)
    await session.flush()

    att = await _upload_attachment(session, test_workspace.id, test_user.id, inv.id)
    await lock_attachment(session, att, locked_by="system", retention_years=5)

    original_until = att.retention_until
    new_until = original_until + timedelta(days=365)

    updated = await update(session, att.id, test_workspace.id, {"retention_until": new_until})
    assert updated.retention_until == new_until


@pytest.mark.asyncio
async def test_fiscal_attachment_auto_locked(session, test_workspace, test_user):
    inv = _make_invoice(session, test_workspace.id, test_user.id)
    await session.flush()

    att = await _upload_attachment(
        session,
        test_workspace.id,
        test_user.id,
        inv.id,
        kind="fiscal",
        source="focus_nfe",
        external_id="chave_123",
    )
    assert att.is_locked is True
    assert att.locked_by == "system"
    assert att.retention_until is not None


@pytest.mark.asyncio
async def test_unlocked_attachment_can_be_deleted(session, test_workspace, test_user):
    inv = _make_invoice(session, test_workspace.id, test_user.id)
    await session.flush()

    att = await _upload_attachment(session, test_workspace.id, test_user.id, inv.id)
    assert att.is_locked is False

    with patch("app.services.invoice_attachment_service.get_storage_provider") as mock_sp:
        mock_storage = AsyncMock()
        mock_sp.return_value = mock_storage
        await delete(session, att.id, test_workspace.id)

    # Verify deletion
    from sqlalchemy import select
    result = await session.execute(
        select(InvoiceAttachment).where(InvoiceAttachment.id == att.id)
    )
    assert result.scalar_one_or_none() is None
