"""The roles of the current workspace, and the catalog of permissions they are made from.

Anyone in the workspace can read the roles (the members screen needs their names). Creating, changing and
deleting the workspace's own roles takes `roles.manage`, which only an owner has unless they give it away.
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import permissions as catalog
from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, current_workspace, require_permission
from app.models.workspace import WorkspaceMember
from app.services import role_service

router = APIRouter(prefix="/api/roles", tags=["roles"])

_manage = require_permission("roles.manage")


class PermissionRead(BaseModel):
    key: str
    group: str


class TemplateRead(BaseModel):
    key: str
    permissions: list[str]


class CatalogRead(BaseModel):
    permissions: list[PermissionRead]
    templates: list[TemplateRead]


class RoleRead(BaseModel):
    #: What a member's `role` holds: `owner`/`editor`/`viewer`, or `c_...` for a workspace's own role.
    key: str
    #: Null for the built-in roles, which are not rows.
    id: Optional[uuid.UUID] = None
    #: Built-in roles have no name of their own here: the interface translates the key.
    name: Optional[str] = None
    description: Optional[str] = None
    system: bool
    permissions: list[str]
    member_count: int = 0


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    permissions: list[str] = []
    #: Start from one of the templates instead of listing permissions (`permissions` are added to it).
    template: Optional[str] = None


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = Field(default=None, max_length=500)
    permissions: Optional[list[str]] = None


def _custom(role, count: int) -> RoleRead:
    return RoleRead(
        key=role.key,
        id=role.id,
        name=role.name,
        description=role.description,
        system=False,
        permissions=sorted(role_service.known_permissions(role.permissions)),
        member_count=count,
    )


@router.get("/catalog", response_model=CatalogRead)
async def permission_catalog(_ctx: WorkspaceContext = Depends(current_workspace)):
    return CatalogRead(
        permissions=[PermissionRead(key=p.key, group=p.group) for p in catalog.PERMISSIONS.values()],
        templates=[TemplateRead(key=t.key, permissions=sorted(t.permissions)) for t in catalog.TEMPLATES],
    )


@router.get("", response_model=list[RoleRead])
async def list_roles(
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    """The built-in roles first, then the workspace's own."""
    counts = {
        role: int(count)
        for role, count in (
            await session.execute(
                select(WorkspaceMember.role, func.count())
                .where(WorkspaceMember.workspace_id == ctx.id)
                .group_by(WorkspaceMember.role)
            )
        ).all()
    }
    built_in = [
        RoleRead(key=key, system=True, permissions=sorted(catalog.SYSTEM_ROLES[key]), member_count=int(counts.get(key, 0)))
        for key in catalog.SYSTEM_ROLE_KEYS
    ]
    return built_in + [_custom(role, count) for role, count in await role_service.list_custom_roles(session, ctx.id)]


@router.post("", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreate,
    ctx: WorkspaceContext = Depends(_manage),
    session: AsyncSession = Depends(get_async_session),
):
    chosen = set(body.permissions)
    if body.template:
        template = next((t for t in catalog.TEMPLATES if t.key == body.template), None)
        if template is None:
            raise HTTPException(status_code=400, detail=f"Unknown template: {body.template}")
        chosen |= template.permissions
    role = await role_service.create_role(
        session,
        ctx.id,
        name=body.name,
        description=body.description,
        permissions=sorted(chosen),
        created_by=ctx.user_id,
    )
    await session.commit()
    return _custom(role, 0)


@router.patch("/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    ctx: WorkspaceContext = Depends(_manage),
    session: AsyncSession = Depends(get_async_session),
):
    role = await role_service.update_role(
        session, ctx.id, role_id, name=body.name, description=body.description, permissions=body.permissions
    )
    await session.commit()
    counts = {r.key: n for r, n in await role_service.list_custom_roles(session, ctx.id)}
    return _custom(role, counts.get(role.key, 0))


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_manage),
    session: AsyncSession = Depends(get_async_session),
):
    await role_service.delete_role(session, ctx.id, role_id)
    await session.commit()
