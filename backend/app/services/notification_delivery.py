"""Getting a notification out of the app: e-mail and webhook.

Both channels are opt-in by configuration (`SMTP_*`, `NOTIFICATIONS_WEBHOOK_URL`)
and both are **best effort**. A mail server that is down must not fail the job
that created the notification, and must not make it retry into a duplicate:
`Notification.delivered_at` is stamped after the attempt whatever the outcome,
because an alert that arrives twice is worse than one that arrives only in the
inbox.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from email.message import EmailMessage

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.notification import Notification
from app.models.user import User
from app.services import email_service

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT_SECONDS = 5.0


def build_message(settings: Settings, to: str, notification: Notification) -> EmailMessage:
    route = (notification.data or {}).get("route", "/")
    return email_service.build_message(
        settings,
        to,
        f"[SyncroFin] {notification.title}",
        f"{notification.title}\n\n{notification.body}\n\n"
        f"Abra o SyncroFin para ver os detalhes: {settings.frontend_url.rstrip('/')}{route}\n",
    )


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def webhook_payload(notification: Notification) -> dict:
    return {
        "id": str(notification.id),
        "workspace_id": str(notification.workspace_id),
        "kind": notification.kind,
        "severity": notification.severity,
        "title": notification.title,
        "body": notification.body,
        "data": notification.data or {},
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


async def _post_webhook(settings: Settings, notification: Notification) -> None:
    body = json.dumps(webhook_payload(notification), ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    secret = settings.notifications_webhook_secret.get_secret_value()
    if secret:
        headers["X-SyncroFin-Signature"] = sign(secret, body)
    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
        response = await client.post(settings.notifications_webhook_url, content=body, headers=headers)
        response.raise_for_status()


async def deliver(session: AsyncSession, notifications: list[Notification]) -> int:
    """Try the configured channels for each new notification. Returns the
    number of notifications that reached at least one channel."""
    settings = get_settings()
    if not (settings.smtp_enabled or settings.notifications_webhook_url):
        return 0

    handed = 0
    now = datetime.now(timezone.utc)
    for notification in notifications:
        if notification.delivered_at is not None:
            continue
        ok = False
        if settings.smtp_enabled:
            user = await session.get(User, notification.user_id)
            if user and user.email:
                try:
                    msg = build_message(settings, user.email, notification)
                    await asyncio.to_thread(email_service.send_blocking, settings, msg)
                    ok = True
                except Exception:
                    logger.exception("E-mail delivery failed for notification %s", notification.id)
        if settings.notifications_webhook_url:
            try:
                await _post_webhook(settings, notification)
                ok = True
            except Exception:
                logger.exception("Webhook delivery failed for notification %s", notification.id)
        notification.delivered_at = now
        handed += 1 if ok else 0
    await session.flush()
    return handed
