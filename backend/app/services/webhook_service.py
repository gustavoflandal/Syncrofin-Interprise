"""CRUD e disparo de webhooks de saída por workspace (F2).

Cada workspace pode registrar vários endpoints. Quando `dispatch` é chamado,
todos os webhooks ativos que subscrevem o evento recebem um POST com o payload
JSON do evento. A entrega é fire-and-forget (asyncio.create_task): falhas não
propagam para o chamador, mas o código de status e o timestamp da última
tentativa são gravados de volta.

Payload padrão:
    {
        "event": "transaction.created",
        "workspace_id": "...",
        "timestamp": "2026-10-06T14:00:00Z",
        "data": { ...payload específico do evento... }
    }

Assinatura (quando `secret` não é vazio):
    X-SyncroFin-Signature: sha256=<hmac-sha256 hex do body>
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_maker
from app.models.workspace_webhook import EVENT_TYPES, WorkspaceWebhook
from app.schemas.webhook import WebhookCreate, WebhookUpdate

logger = logging.getLogger(__name__)

_TIMEOUT = 8.0


# ── CRUD ─────────────────────────────────────────────────────────────────────


async def list_webhooks(session: AsyncSession, workspace_id: uuid.UUID) -> list[WorkspaceWebhook]:
    rows = await session.execute(
        select(WorkspaceWebhook)
        .where(WorkspaceWebhook.workspace_id == workspace_id)
        .order_by(WorkspaceWebhook.created_at)
    )
    return list(rows.scalars().all())


async def get_webhook(
    session: AsyncSession, webhook_id: uuid.UUID, workspace_id: uuid.UUID
) -> Optional[WorkspaceWebhook]:
    row = await session.execute(
        select(WorkspaceWebhook).where(
            WorkspaceWebhook.id == webhook_id,
            WorkspaceWebhook.workspace_id == workspace_id,
        )
    )
    return row.scalar_one_or_none()


async def create_webhook(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    data: WebhookCreate,
) -> WorkspaceWebhook:
    wh = WorkspaceWebhook(
        workspace_id=workspace_id,
        created_by=user_id,
        url=str(data.url),
        secret=data.secret or None,
        event_types=data.event_types or None,
        active=True,
    )
    session.add(wh)
    await session.flush()
    return wh


async def update_webhook(
    session: AsyncSession,
    webhook: WorkspaceWebhook,
    data: WebhookUpdate,
) -> WorkspaceWebhook:
    if data.url is not None:
        webhook.url = str(data.url)
    if data.secret is not None:
        webhook.secret = data.secret or None
    if data.event_types is not None:
        webhook.event_types = data.event_types or None
    if data.active is not None:
        webhook.active = data.active
    await session.flush()
    return webhook


async def delete_webhook(session: AsyncSession, webhook: WorkspaceWebhook) -> None:
    await session.delete(webhook)
    await session.flush()


# ── Dispatch ─────────────────────────────────────────────────────────────────


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _build_payload(workspace_id: uuid.UUID, event_type: str, data: dict[str, Any]) -> bytes:
    envelope = {
        "event": event_type,
        "workspace_id": str(workspace_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    return json.dumps(envelope, ensure_ascii=False, default=str).encode("utf-8")


async def _deliver_one(webhook_id: uuid.UUID, url: str, secret: Optional[str], body: bytes) -> int:
    """POST the payload to one URL. Returns the HTTP status code (or 0 on error)."""
    headers: dict[str, str] = {"Content-Type": "application/json; charset=utf-8"}
    if secret:
        headers["X-SyncroFin-Signature"] = _sign(secret, body)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, content=body, headers=headers)
            return resp.status_code
    except Exception:
        logger.exception("Webhook delivery error (id=%s url=%s)", webhook_id, url)
        return 0


async def _deliver_and_record(webhook_id: uuid.UUID, url: str, secret: Optional[str], body: bytes) -> None:
    """Deliver and write status back to the database using a fresh session."""
    status_code = await _deliver_one(webhook_id, url, secret, body)
    try:
        async with async_session_maker() as session:
            wh = await session.get(WorkspaceWebhook, webhook_id)
            if wh is not None:
                wh.last_fired_at = datetime.now(timezone.utc)
                wh.last_status_code = status_code
                await session.commit()
    except Exception:
        logger.exception("Failed to record webhook delivery status (id=%s)", webhook_id)


def dispatch(
    workspace_id: uuid.UUID,
    event_type: str,
    data: dict[str, Any],
    webhooks: list[WorkspaceWebhook],
) -> None:
    """Fire-and-forget: schedule delivery for all matching active webhooks.

    Must be called from inside a running event loop (i.e., inside a FastAPI
    request). The caller provides the already-loaded list of webhooks so
    this function does not need its own session — it schedules background
    tasks and returns immediately.
    """
    if event_type not in EVENT_TYPES:
        logger.warning("Unknown webhook event type: %s", event_type)
        return

    body = _build_payload(workspace_id, event_type, data)

    for wh in webhooks:
        if not wh.active:
            continue
        subscribed = wh.event_types
        if subscribed and event_type not in subscribed:
            continue
        asyncio.create_task(
            _deliver_and_record(wh.id, wh.url, wh.secret, body),
            name=f"webhook:{wh.id}:{event_type}",
        )


async def load_and_dispatch(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Load active webhooks from the DB and dispatch. Convenience wrapper."""
    whs = await session.execute(
        select(WorkspaceWebhook).where(
            WorkspaceWebhook.workspace_id == workspace_id,
            WorkspaceWebhook.active.is_(True),
        )
    )
    dispatch(workspace_id, event_type, data, list(whs.scalars().all()))
