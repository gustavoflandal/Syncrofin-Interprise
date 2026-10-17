"""Who is acting, for the audit trail.

Kept apart from `core/audit.py` (which imports every model) so that the
authentication code can report the actor without an import cycle.
"""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class AuditContext:
    """Filled in as the request goes through the middleware and the auth dependency."""

    actor_user_id: uuid.UUID | None = None
    actor_kind: str = "system"
    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
    # Set when the request authenticated with an API token (services/api_token_service.py).
    api_token_id: uuid.UUID | None = None
    api_token_prefix: str | None = None
    api_token_scopes: frozenset[str] = frozenset()
    api_token_workspace_id: uuid.UUID | None = None


# Mutable on purpose: the middleware sets it before the route runs, a dependency fills in the
# user later. Dependencies run in a copied context, so replacing the value would not be seen by
# the code that saves; mutating the shared object is.
audit_context: ContextVar[AuditContext | None] = ContextVar("audit_context", default=None)


def current_context() -> AuditContext:
    """The request's context, or a blank one (a background job) that changes nothing shared."""
    return audit_context.get() or AuditContext()


def set_actor(user_id: uuid.UUID, kind: str = "user") -> None:
    ctx = audit_context.get()
    if ctx is not None:  # outside a request there is nothing to attribute
        ctx.actor_user_id = user_id
        ctx.actor_kind = kind
