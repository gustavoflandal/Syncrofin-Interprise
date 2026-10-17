"""FastAPI dependency that resolves the current workspace for a request.

Resolution order:
  1. `X-Workspace-Id` header — explicit selection from the frontend.
  2. The user's first/default workspace (`get_default_workspace`).

If neither resolves, raises 404. Returns a `WorkspaceContext` value
object that carries the workspace + the requester's membership + the
inferred role. Routes that mutate data check `ctx.role` to enforce
viewer/editor/owner restrictions; routes that just read use any
membership.
"""
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import permissions as catalog
from app.core.audit_context import current_context
from app.core.auth import current_principal
from app.core.database import get_async_session
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services.workspace_service import (
    _virtual_manager_member,
    get_default_workspace,
    get_membership,
    is_workspace_manager,
)


@dataclass
class WorkspaceContext:
    workspace: Workspace
    member: WorkspaceMember
    user: User
    #: What the member's role allows (core/permissions.py). Left out, it is the role's own set for
    #: the built-in roles; a custom role's set is looked up and passed in by `current_workspace`.
    permissions: Optional[frozenset[str]] = None

    def __post_init__(self) -> None:
        if self.permissions is None:
            self.permissions = catalog.SYSTEM_ROLES.get(self.member.role, frozenset())

    @property
    def id(self) -> uuid.UUID:
        return self.workspace.id

    @property
    def user_id(self) -> uuid.UUID:
        """The current human's user_id — used as `created_by` on new rows."""
        return self.user.id

    @property
    def role(self) -> str:
        return self.member.role

    def can(self, permission: str) -> bool:
        return permission in (self.permissions or frozenset())

    @property
    def can_write(self) -> bool:
        """May change *something* in the workspace's data (holds at least one write permission)."""
        return bool((self.permissions or frozenset()) & catalog.WRITE_PERMISSIONS)

    @property
    def is_owner(self) -> bool:
        # Administers the workspace: an owner, a manager from outside, or a custom role with the permission.
        return self.can("workspace.manage")

    def require(self, permission: str) -> None:
        if not self.can(permission):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")

    def require_write(self) -> None:
        if not self.can_write:
            raise HTTPException(status_code=403, detail="Read-only role")

    def require_owner(self) -> None:
        if not self.is_owner:
            raise HTTPException(status_code=403, detail="Owner role required")


async def _context(
    session: AsyncSession, workspace: Workspace, member: WorkspaceMember, user: User
) -> WorkspaceContext:
    from app.services import role_service

    permissions = await role_service.permissions_of(session, workspace.id, member.role)
    token = current_context()
    if token.api_token_id is not None:
        # At most what the token was given, and at most what its owner can do right now.
        permissions = permissions & token.api_token_scopes
    return WorkspaceContext(workspace=workspace, member=member, user=user, permissions=permissions)


async def _check_workspace_mfa(
    request: Request, workspace: Workspace, user: User, session: AsyncSession
) -> None:
    """Raise 403 if the workspace requires MFA and this session has not proved it.

    Applies only to browser sessions; API tokens are excluded (a token with narrow scope
    is already a strong credential — requiring a second factor on top would break automation).
    """
    if not workspace.mfa_required:
        return
    token = current_context()
    if token.api_token_id is not None:
        return  # API token: skip
    from app.models.user_session import UserSession
    from app.services import mfa_policy, session_service
    if mfa_policy.is_enrolment_route(request.method, request.url.path):
        return
    sid = session_service.session_id_from_request(request)
    row = await session.get(UserSession, sid) if sid else None
    if row is None or not row.mfa_verified:
        raise HTTPException(status_code=403, detail="MFA_ENROLLMENT_REQUIRED")


async def current_workspace(
    request: Request,
    x_workspace_id: Optional[str] = Header(default=None, alias="X-Workspace-Id"),
    user: User = Depends(current_principal),
    session: AsyncSession = Depends(get_async_session),
) -> WorkspaceContext:
    """Dependency: resolve and validate the current workspace + membership."""
    token = current_context()
    if token.api_token_id is not None:
        # A token belongs to one workspace. Naming another is an error, not a redirect.
        bound = str(token.api_token_workspace_id)
        if x_workspace_id and x_workspace_id != bound:
            raise HTTPException(status_code=403, detail="This API token belongs to another workspace")
        x_workspace_id = bound
    if x_workspace_id:
        try:
            ws_uuid = uuid.UUID(x_workspace_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid X-Workspace-Id")
        workspace = await session.get(Workspace, ws_uuid)
        if workspace is None or workspace.is_archived:
            raise HTTPException(status_code=404, detail="Workspace not found")
        member = await get_membership(session, ws_uuid, user.id)
        if member is None:
            # Fall back to manager-of access.
            if await is_workspace_manager(session, ws_uuid, user.id):
                member = _virtual_manager_member(ws_uuid, user.id)
            else:
                raise HTTPException(status_code=404, detail="Workspace not found")
        await _check_workspace_mfa(request, workspace, user, session)
        return await _context(session, workspace, member, user)

    # Fallback: user's first non-archived workspace (member-of or managed).
    default = await get_default_workspace(session, user.id)
    if default is None:
        raise HTTPException(status_code=404, detail="No workspace available")
    member = await get_membership(session, default.id, user.id)
    if member is None:
        # Managed-only workspace path.
        if await is_workspace_manager(session, default.id, user.id):
            member = _virtual_manager_member(default.id, user.id)
        else:
            raise HTTPException(status_code=500, detail="Workspace state inconsistent")
    await _check_workspace_mfa(request, default, user, session)
    return await _context(session, default, member, user)


# Convenience: write-gated context. Raises 403 if the user can't write.
async def current_writable_workspace(
    ctx: WorkspaceContext = Depends(current_workspace),
) -> WorkspaceContext:
    ctx.require_write()
    return ctx


def require_permission(permission: str) -> Callable[..., Awaitable[WorkspaceContext]]:
    """A route that needs `permission` in the current workspace (403 without it).

    The gate function is always named `permission_gate` and carries the permission it asks for, so
    the route-coverage test can see that every mutating route asks for one that exists.
    """
    if permission not in catalog.ALL_PERMISSIONS:
        raise ValueError(f"Unknown permission: {permission}")

    async def permission_gate(ctx: WorkspaceContext = Depends(current_workspace)) -> WorkspaceContext:
        ctx.require(permission)
        return ctx

    setattr(permission_gate, "permission", permission)
    return permission_gate
