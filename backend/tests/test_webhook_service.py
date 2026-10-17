"""Unit tests for webhook_service (F2).

Covers CRUD, dispatch fan-out, HMAC signing, and redeliver.
HTTP calls are stubbed with respx so no real network is involved.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import WebhookDelivery, WebhookEndpoint
from app.models.workspace import Workspace, WorkspaceMember
from app.services import webhook_service


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _make_workspace(session: AsyncSession) -> Workspace:
    ws = Workspace(
        id=uuid.uuid4(),
        name="TestWS",
        kind="personal",
        created_by_user_id=uuid.uuid4(),
        default_currency="BRL",
        locale="pt-BR",
    )
    session.add(ws)
    await session.flush()
    return ws


async def _make_endpoint(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    url: str = "https://example.com/hook",
    events: list[str] | None = None,
    secret: str | None = "s3cr3t",
    is_active: bool = True,
) -> WebhookEndpoint:
    ep = await webhook_service.create_endpoint(
        session, workspace_id, url, secret, events or ["transaction.created"]
    )
    if not is_active:
        ep.is_active = False
        await session.flush()
    return ep


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_list_endpoint(session: AsyncSession, clean_db):
    ws = await _make_workspace(session)
    ep = await _make_endpoint(session, ws.id, events=["transaction.created", "invoice.paid"])
    await session.commit()

    endpoints = await webhook_service.list_endpoints(session, ws.id)
    assert len(endpoints) == 1
    assert endpoints[0].id == ep.id
    assert "invoice.paid" in endpoints[0].events


@pytest.mark.asyncio
async def test_get_endpoint_wrong_workspace(session: AsyncSession, clean_db):
    ws = await _make_workspace(session)
    ep = await _make_endpoint(session, ws.id)
    await session.commit()

    result = await webhook_service.get_endpoint(session, ep.id, uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_update_endpoint(session: AsyncSession, clean_db):
    ws = await _make_workspace(session)
    ep = await _make_endpoint(session, ws.id, events=["transaction.created"])
    await session.commit()

    ep = await webhook_service.update_endpoint(
        session, ep, events=["invoice.paid"], is_active=False
    )
    await session.commit()

    assert ep.events == ["invoice.paid"]
    assert ep.is_active is False


@pytest.mark.asyncio
async def test_delete_endpoint(session: AsyncSession, clean_db):
    ws = await _make_workspace(session)
    ep = await _make_endpoint(session, ws.id)
    await session.commit()

    await webhook_service.delete_endpoint(session, ep)
    await session.commit()

    endpoints = await webhook_service.list_endpoints(session, ws.id)
    assert endpoints == []


# ---------------------------------------------------------------------------
# dispatch_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_fires_to_subscribed_endpoint(session: AsyncSession, clean_db):
    ws = await _make_workspace(session)
    await _make_endpoint(session, ws.id, url="https://hook.example.com/rx", events=["transaction.created"])
    await session.commit()

    respx.post("https://hook.example.com/rx").mock(return_value=Response(200))

    count = await webhook_service.dispatch_event(
        session, ws.id, "transaction.created", {"id": "abc"}
    )
    assert count == 1

    deliveries = await webhook_service.list_deliveries(session, (await webhook_service.list_endpoints(session, ws.id))[0].id)
    assert len(deliveries) == 1
    assert deliveries[0].http_status == 200
    assert deliveries[0].delivered_at is not None


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_skips_unsubscribed_event(session: AsyncSession, clean_db):
    ws = await _make_workspace(session)
    await _make_endpoint(session, ws.id, events=["invoice.paid"])
    await session.commit()

    count = await webhook_service.dispatch_event(
        session, ws.id, "transaction.created", {"id": "xyz"}
    )
    assert count == 0


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_skips_inactive_endpoint(session: AsyncSession, clean_db):
    ws = await _make_workspace(session)
    await _make_endpoint(session, ws.id, is_active=False)
    await session.commit()

    count = await webhook_service.dispatch_event(
        session, ws.id, "transaction.created", {}
    )
    assert count == 0


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_endpoint_with_empty_events_receives_all(session: AsyncSession, clean_db):
    """An endpoint with events=[] subscribes to every event."""
    ws = await _make_workspace(session)
    await _make_endpoint(session, ws.id, events=[])
    await session.commit()

    respx.post("https://example.com/hook").mock(return_value=Response(204))

    count = await webhook_service.dispatch_event(
        session, ws.id, "sync.completed", {"connection_id": "x"}
    )
    assert count == 1


@pytest.mark.asyncio
@respx.mock
async def test_dispatch_records_failed_delivery(session: AsyncSession, clean_db):
    ws = await _make_workspace(session)
    ep = await _make_endpoint(session, ws.id)
    await session.commit()

    respx.post("https://example.com/hook").mock(return_value=Response(500, text="Server Error"))

    await webhook_service.dispatch_event(session, ws.id, "transaction.created", {})

    deliveries = await webhook_service.list_deliveries(session, ep.id)
    assert deliveries[0].http_status == 500
    assert deliveries[0].delivered_at is None
    assert "500" in (deliveries[0].last_error or "")


# ---------------------------------------------------------------------------
# HMAC signing
# ---------------------------------------------------------------------------


def test_sign_produces_sha256_prefix():
    sig = webhook_service._sign("secret", b"payload")
    assert sig.startswith("sha256=")
    assert len(sig) > 10


def test_sign_is_deterministic():
    assert webhook_service._sign("s", b"p") == webhook_service._sign("s", b"p")


def test_sign_differs_for_different_secrets():
    assert webhook_service._sign("a", b"p") != webhook_service._sign("b", b"p")


# ---------------------------------------------------------------------------
# redeliver
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_redeliver_retries_delivery(session: AsyncSession, clean_db):
    ws = await _make_workspace(session)
    ep = await _make_endpoint(session, ws.id, url="https://retry.example.com/hook")
    await session.commit()

    # First dispatch fails
    respx.post("https://retry.example.com/hook").mock(return_value=Response(503))
    await webhook_service.dispatch_event(session, ws.id, "transaction.created", {})

    deliveries = await webhook_service.list_deliveries(session, ep.id)
    delivery = deliveries[0]
    assert delivery.http_status == 503

    # Redeliver succeeds
    respx.post("https://retry.example.com/hook").mock(return_value=Response(200))
    updated = await webhook_service.redeliver(session, delivery, ep)
    assert updated.http_status == 200
    assert updated.attempt_count == 2
