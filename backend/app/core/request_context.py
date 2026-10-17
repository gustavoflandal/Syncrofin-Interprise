"""Gives every request an id and tells the audit trail where it came from."""
from __future__ import annotations

import uuid

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.audit_context import AuditContext, audit_context
from app.core.config import get_settings
from app.core.rate_limit import resolve_client_ip


class RequestContextMiddleware:
    """Pure ASGI (not `BaseHTTPMiddleware`): the context it sets must reach the route."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        request_id = uuid.uuid4().hex
        token = audit_context.set(
            AuditContext(
                ip=resolve_client_ip(request, get_settings().trusted_proxy_hops),
                user_agent=request.headers.get("user-agent"),
                request_id=request_id,
            )
        )

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            audit_context.reset(token)
