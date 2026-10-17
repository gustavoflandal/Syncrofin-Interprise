"""Roles: which permissions a member holds, and the workspace's own roles.

`permissions_of` is what the request path uses (one lookup, only for a member with a custom role: the
product's own roles are answered from `core/permissions.py` with no query). The rest is what the roles screen
does: list, create, change and delete a workspace's custom roles.
"""
from __future__ import annotations

import secrets
import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import permissions as catalog
from app.models.workspace import WorkspaceMember
from app.models.workspace_role import CUSTOM_KEY_PREFIX, WorkspaceRole

MAX_CUSTOM_ROLES = 30


async def get_custom_role(session: AsyncSession, workspace_id: uuid.UUID, key: str) -> WorkspaceRole | None:
    if not key.startswith(CUSTOM_KEY_PREFIX):
        return None
    return (
        await session.execute(
            select(WorkspaceRole).where(WorkspaceRole.workspace_id == workspace_id, WorkspaceRole.key == key)
        )
    ).scalar_one_or_none()


def known_permissions(permissions: list[str] | None) -> frozenset[str]:
    """A stored role's permissions minus any the catalog no longer has."""
    return frozenset(permissions or []) & catalog.ALL_PERMISSIONS


async def permissions_of(session: AsyncSession, workspace_id: uuid.UUID, role_key: str) -> frozenset[str]:
    """What holding `role_key` in this workspace allows. An unknown key allows nothing."""
    if catalog.is_system_role(role_key):
        return catalog.SYSTEM_ROLES[role_key]
    role = await get_custom_role(session, workspace_id, role_key)
    return known_permissions(role.permissions) if role else frozenset()


async def require_assignable(session: AsyncSession, workspace_id: uuid.UUID, role_key: str) -> None:
    """A member can be given `owner`, `editor`, `viewer`, or one of this workspace's own roles."""
    if role_key in catalog.SYSTEM_ROLE_KEYS:
        return
    if await get_custom_role(session, workspace_id, role_key) is None:
        raise HTTPException(status_code=400, detail=f"Invalid role: {role_key}")


async def list_custom_roles(session: AsyncSession, workspace_id: uuid.UUID) -> list[tuple[WorkspaceRole, int]]:
    """The workspace's own roles, each with how many members hold it."""
    roles = (
        await session.execute(
            select(WorkspaceRole).where(WorkspaceRole.workspace_id == workspace_id).order_by(WorkspaceRole.name)
        )
    ).scalars().all()
    counts = {
        role: int(count)
        for role, count in (
            await session.execute(
                select(WorkspaceMember.role, func.count())
                .where(WorkspaceMember.workspace_id == workspace_id)
                .group_by(WorkspaceMember.role)
            )
        ).all()
    }
    return [(role, int(counts.get(role.key, 0))) for role in roles]


async def _name_taken(session: AsyncSession, workspace_id: uuid.UUID, name: str, except_id: uuid.UUID | None) -> bool:
    query = select(WorkspaceRole.id).where(
        WorkspaceRole.workspace_id == workspace_id, func.lower(WorkspaceRole.name) == name.strip().lower()
    )
    if except_id:
        query = query.where(WorkspaceRole.id != except_id)
    return (await session.execute(query.limit(1))).first() is not None


async def create_role(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    name: str,
    description: str | None,
    permissions: list[str],
    created_by: uuid.UUID,
) -> WorkspaceRole:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="A role needs a name")
    if name.lower() in catalog.SYSTEM_ROLE_KEYS or name.lower() == "manager":
        raise HTTPException(status_code=409, detail="That name belongs to a built-in role")
    try:
        chosen = catalog.normalise(permissions)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if await _name_taken(session, workspace_id, name, None):
        raise HTTPException(status_code=409, detail="A role with this name already exists")
    existing = (
        await session.execute(select(func.count()).select_from(WorkspaceRole).where(WorkspaceRole.workspace_id == workspace_id))
    ).scalar_one()
    if existing >= MAX_CUSTOM_ROLES:
        raise HTTPException(status_code=400, detail=f"A workspace can have at most {MAX_CUSTOM_ROLES} custom roles")
    role = WorkspaceRole(
        workspace_id=workspace_id,
        key=CUSTOM_KEY_PREFIX + secrets.token_hex(4),
        name=name,
        description=(description or "").strip() or None,
        permissions=sorted(chosen),
        created_by_user_id=created_by,
    )
    session.add(role)
    await session.flush()
    return role


async def update_role(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
    *,
    name: str | None,
    description: str | None,
    permissions: list[str] | None,
) -> WorkspaceRole:
    role = await session.get(WorkspaceRole, role_id)
    if role is None or role.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Role not found")
    if name is not None:
        name = name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="A role needs a name")
        if name.lower() in catalog.SYSTEM_ROLE_KEYS or name.lower() == "manager":
            raise HTTPException(status_code=409, detail="That name belongs to a built-in role")
        if await _name_taken(session, workspace_id, name, role.id):
            raise HTTPException(status_code=409, detail="A role with this name already exists")
        role.name = name
    if description is not None:
        role.description = description.strip() or None
    if permissions is not None:
        try:
            role.permissions = sorted(catalog.normalise(permissions))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    await session.flush()
    return role


async def delete_role(session: AsyncSession, workspace_id: uuid.UUID, role_id: uuid.UUID) -> None:
    role = await session.get(WorkspaceRole, role_id)
    if role is None or role.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Role not found")
    holders = (
        await session.execute(
            select(func.count()).select_from(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.role == role.key
            )
        )
    ).scalar_one()
    if holders:
        # Deleting it would leave those members with a role that allows nothing.
        raise HTTPException(status_code=409, detail="Members still hold this role: move them to another first")
    await session.delete(role)
    await session.flush()
