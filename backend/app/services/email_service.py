"""Sending e-mail, for the messages people must receive to use the product.

Notifications have their own best-effort channel (`notification_delivery`); this
is for **transactional** mail: a password-reset link, a workspace invitation.
Those differ in one way that matters: if they do not arrive, the person is
stuck, so a failure is logged loudly and reported to the caller rather than
swallowed.

Plain text only, on purpose. There is no HTML to escape, no remote image to
track anyone with, and the link the person needs is a bare URL every client
makes clickable. The recipient's address is validated upstream, and every value
that lands in a header is stripped of line breaks here, so a workspace called
"X\\r\\nBcc: attacker@example.com" cannot smuggle a header.

The link's host always comes from `FRONTEND_URL`, never from the incoming
request: a `Host:` header the client controls must not decide where a
password-reset link points.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Optional

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_SECONDS = 10.0


def is_enabled(settings: Optional[Settings] = None) -> bool:
    return (settings or get_settings()).smtp_enabled


def clean_header(value: str, limit: int = 120) -> str:
    """One line, bounded. Anything that could start a new header is removed."""
    return " ".join(str(value).split())[:limit]


def frontend_link(path: str, **params: str) -> str:
    """`{FRONTEND_URL}{path}?k=v`, built from configuration only."""
    from urllib.parse import urlencode

    base = get_settings().frontend_url.rstrip("/")
    query = f"?{urlencode(params)}" if params else ""
    return f"{base}{path}{query}"


def build_message(settings: Settings, to: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = clean_header(subject, 200)
    msg["From"] = settings.smtp_from
    msg["To"] = clean_header(to, 320)
    msg.set_content(body)
    return msg


def send_blocking(settings: Settings, msg: EmailMessage) -> None:
    """Hand a message to the SMTP server. Blocking; run it in a thread."""
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        smtp.send_message(msg)


async def send(to: str, subject: str, body: str) -> bool:
    """Send one message. True when the SMTP server accepted it.

    False when e-mail is not configured or the server refused: the caller
    decides whether that is fatal (an invitation can still be given a
    password out of band) or merely worth a log line. Never raises for a
    delivery problem, and never logs the body: it holds a live token.
    """
    settings = get_settings()
    if not is_enabled(settings):
        logger.warning("E-mail is not configured (SMTP_HOST / SMTP_FROM); message to a user was not sent")
        return False
    try:
        msg = build_message(settings, to, subject, body)
        await asyncio.to_thread(send_blocking, settings, msg)
        return True
    except Exception:
        logger.exception("Could not send e-mail")
        return False


# Fire-and-forget sends are held here so the event loop cannot garbage-collect a
# running task, and so tests can wait for them (`drain`).
_pending: set[asyncio.Task] = set()


def send_in_background(to: str, subject: str, body: str) -> None:
    """Send without making the caller wait for the SMTP round trip.

    For requests where the *time it takes* would tell a stranger something. The
    password-reset endpoint answers the same way, at the same speed, whether or
    not the address has an account; awaiting the mail only for real accounts
    would let anyone tell them apart with a stopwatch.
    """
    task = asyncio.get_running_loop().create_task(send(to, subject, body))
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def drain() -> None:
    """Wait for every background send to finish. Tests only."""
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)
