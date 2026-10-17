"""Workspace + member management endpoints.

Every user gets a Personal workspace at registration. `POST` here
creates the additional ones and is the only place `kind` is ever set;
`PATCH` edits the rest of the workspace and deliberately cannot touch
it.
"""
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import Response
from fastapi_users import schemas as fu_schemas
from fastapi_users.exceptions import InvalidPasswordException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.upload_guard import validate_upload
from app.core import password_policy
from app.core import permissions as catalog
from app.core.auth import (
    INVITE_TOKEN_LIFETIME_SECONDS,
    UserManager,
    current_active_user,
    get_user_manager,
)
from app.core.auth_policy import local_auth_enabled, require_local_auth_enabled
from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, current_workspace
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceTaxId
from app.schemas.workspace import (
    MemberInvite,
    MemberRead,
    MemberRoleUpdate,
    WorkspaceCreate,
    WorkspaceRead,
    WorkspaceSetup,
    WorkspaceUpdate,
)
from app.services import account_service, email_service, email_templates, module_service, role_service, workspace_service

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


def _user_display_name(user: User) -> str | None:
    prefs = user.preferences or {}
    return prefs.get("display_name") or None


def _workspace_read(
    workspace: Workspace, role: str | None, permissions: frozenset[str] | None = None
) -> WorkspaceRead:
    """Build the read model for a workspace.

    Every response that returns a workspace goes through here, so a new
    read path cannot ship without `enabled_modules` — forgetting it
    would leave the frontend hiding modules the server enabled.
    """
    item = WorkspaceRead.model_validate(workspace)
    item.role = role
    # A built-in role is answered from code; a workspace's own role passes its looked-up set in.
    if permissions is None:
        permissions = catalog.SYSTEM_ROLES.get(role or "", frozenset())
    item.permissions = sorted(permissions)
    item.enabled_modules = module_service.resolve_modules(workspace)
    return item


@router.get("", response_model=list[WorkspaceRead])
async def list_my_workspaces(
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Return every workspace the current user can access.

    Unions two sets:
      - workspaces where the user has a `workspace_members` row (role
        comes from that row)
      - workspaces where `workspaces.managed_by_user_id` matches the
        user but they have no membership (role = 'manager')

    A user who is both a member AND the external manager is reported
    with their concrete membership role (not the virtual manager one)
    since their explicit role is the more specific signal.
    """
    member_rows = await session.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(
            WorkspaceMember.user_id == user.id,
            Workspace.is_archived.is_(False),
        )
        .order_by(Workspace.created_at.asc())
    )
    out: list[WorkspaceRead] = []
    seen_ids: set[uuid.UUID] = set()
    for ws, role in member_rows.all():
        permissions = None if catalog.is_system_role(role) else await role_service.permissions_of(session, ws.id, role)
        out.append(_workspace_read(ws, role, permissions))
        seen_ids.add(ws.id)

    managed_rows = await session.execute(
        select(Workspace)
        .where(
            Workspace.managed_by_user_id == user.id,
            Workspace.is_archived.is_(False),
        )
        .order_by(Workspace.created_at.asc())
    )
    for ws in managed_rows.scalars().all():
        if ws.id in seen_ids:
            continue
        out.append(_workspace_read(ws, "manager"))
    return out


@router.post("", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
async def create_workspace_endpoint(
    body: WorkspaceCreate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Create a new workspace; the caller becomes its manager.

    Use case: a user provisioning a workspace they'll operate (either
    for themselves as a second container, or on behalf of someone else
    who'll be invited later as the day-to-day owner).
    """
    workspace = await workspace_service.create_workspace(
        session,
        name=body.name,
        creator=user,
        kind=body.kind,
        default_currency=body.default_currency,
        locale=body.locale,
        tax_jurisdiction=body.tax_jurisdiction,
        icon=body.icon,
        color=body.color,
        self_membership=body.self_membership,
    )
    await session.commit()
    return _workspace_read(workspace, "owner" if body.self_membership else "manager")


@router.get("/current", response_model=WorkspaceRead)
async def get_current_workspace(ctx: WorkspaceContext = Depends(current_workspace)):
    """Return the workspace resolved from X-Workspace-Id (or the default)."""
    return _workspace_read(ctx.workspace, ctx.role, ctx.permissions)


@router.patch("/{workspace_id}", response_model=WorkspaceRead)
async def update_workspace(
    workspace_id: uuid.UUID,
    body: WorkspaceUpdate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    member = await workspace_service.require_membership(
        session, workspace_id, user.id, permission="workspace.manage"
    )
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(workspace, key, value)
    # Changing the workspace currency follows through to the acting
    # owner's display currency, so the whole app re-renders in the new
    # currency (display is driven by user.currency_display, not the
    # workspace). Other members keep their own currency_display override.
    new_currency = updates.get("default_currency")
    if new_currency and (user.preferences or {}).get("currency_display") != new_currency:
        prefs = dict(user.preferences or {})
        prefs["currency_display"] = new_currency
        user.preferences = prefs
        session.add(user)
    await session.commit()
    await session.refresh(workspace)
    return _workspace_read(
        workspace, member.role, await role_service.permissions_of(session, workspace_id, member.role)
    )


@router.get("/{workspace_id}/members", response_model=list[MemberRead])
async def list_workspace_members(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    # Any member can list members of their own workspace.
    await workspace_service.require_membership(session, workspace_id, user.id)
    rows = await workspace_service.list_members(session, workspace_id)
    return [
        MemberRead(
            id=m.id,
            user_id=u.id,
            email=u.email,
            display_name=_user_display_name(u),
            role=m.role,
            joined_at=m.joined_at,
        )
        for m, u in rows
    ]


@router.get("/{workspace_id}/accounts", response_model=list[dict])
async def list_workspace_accounts(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """List accounts of any workspace the requesting user is a member of.

    Used by the A9 cross-workspace transfer dialog to populate destination
    account options without requiring the user to switch workspaces.
    """
    await workspace_service.require_membership(session, workspace_id, user.id)
    accounts = await account_service.get_accounts(session, workspace_id)
    return accounts


@router.post(
    "/{workspace_id}/members",
    response_model=MemberRead,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    workspace_id: uuid.UUID,
    body: MemberInvite,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
    user_manager: UserManager = Depends(get_user_manager),
):
    await workspace_service.require_membership(
        session, workspace_id, user.id, permission="members.manage"
    )

    # Find existing user by email (case-insensitive — fastapi-users
    # stores email lowercased on register, but be safe).
    existing = await session.execute(
        select(User).where(User.email == body.email.lower())
    )
    target = existing.scalar_one_or_none()

    created_new = False
    invited_without_password = False
    if target is None:
        # Brand-new user — creating the account here mints a local password,
        # so it is only allowed while local credentials are accepted.
        password = body.password
        if password:
            require_local_auth_enabled()
        elif not local_auth_enabled():
            # There is no password to ask for in OIDC-only mode, so point at
            # what actually unblocks the invite.
            raise HTTPException(
                status_code=400,
                detail=(
                    "User not found. They must sign in through the identity "
                    "provider once before they can be added."
                ),
            )
        elif email_service.is_enabled():
            # Invitation by e-mail: the account is created with a password
            # nobody knows, and the message carries a one-time link to choose
            # a real one. The owner never has to invent and relay a password.
            password = secrets.token_urlsafe(32)
            invited_without_password = True
        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    "User not found. Provide a password to create them, or "
                    "configure e-mail (SMTP) to invite them by link."
                ),
            )
        try:
            # Stored lowercased, matching the lookup above: an account created as
            # "Ana@X.com" would otherwise never be found again by "ana@x.com".
            create_payload = fu_schemas.BaseUserCreate(
                email=body.email.lower(),
                password=password,
            )
            target = await user_manager.create(create_payload)
            created_new = True
            # A user created to join this workspace inherits its currency
            # as their display currency, so the app comes up in the
            # workspace's currency rather than the USD default. Set this
            # before bootstrapping their Personal workspace below, which
            # reads currency_display for its own default_currency.
            ws = await session.get(Workspace, workspace_id)
            if ws is not None:
                target.preferences = {
                    **(target.preferences or {}),
                    "currency_display": ws.default_currency,
                }
                session.add(target)
                await session.flush()
            # The fresh user gets their own Personal workspace by virtue
            # of the registration hook (called below via on_after_register
            # when request is non-None; programmatic call leaves it empty,
            # so we bootstrap explicitly).
            await workspace_service.create_personal_workspace_for_user(session, target)
        except InvalidPasswordException as e:
            raise HTTPException(status_code=400, detail=password_policy.http_detail(str(e.reason)))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not create user: {e}")

    member = await workspace_service.add_member(
        session,
        workspace_id=workspace_id,
        user_id=target.id,
        role=body.role,
        invited_by_user_id=user.id,
    )
    await session.commit()

    email_sent = await _send_invitation_email(
        session,
        workspace_id=workspace_id,
        inviter=user,
        invitee=target,
        role=member.role,
        user_manager=user_manager,
        created_new=created_new,
        invited_without_password=invited_without_password,
    )
    return MemberRead(
        id=member.id,
        user_id=target.id,
        email=target.email,
        display_name=_user_display_name(target),
        role=member.role,
        joined_at=member.joined_at,
        invitation_email_sent=email_sent,
    )


async def _send_invitation_email(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    inviter: User,
    invitee: User,
    role: str,
    user_manager: UserManager,
    created_new: bool,
    invited_without_password: bool,
) -> bool:
    """E-mail the invitee, when the server can. Never fails the invitation.

    Three cases, three links: a brand-new account with no password yet gets a
    one-time link to choose one; an account whose password the owner set, or a
    person who already had an account, is simply pointed at the app.
    """
    if not email_service.is_enabled():
        return False
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        return False

    if invited_without_password:
        token = user_manager.issue_reset_token(invitee, INVITE_TOKEN_LIFETIME_SECONDS)
        link = email_service.frontend_link("/reset-password", token=token, invited="1")
        language = (inviter.preferences or {}).get("language")
    else:
        link = email_service.frontend_link("/login" if created_new else "/")
        language = (invitee.preferences or {}).get("language") or (inviter.preferences or {}).get("language")

    subject, text = email_templates.workspace_invite(
        language,
        inviter=_user_display_name(inviter) or inviter.email,
        workspace=workspace.name,
        role=role,
        link=link,
        new_account=invited_without_password,
        days=INVITE_TOKEN_LIFETIME_SECONDS // 86400,
    )
    return await email_service.send(invitee.email, subject, text)


@router.patch(
    "/{workspace_id}/members/{member_user_id}",
    response_model=MemberRead,
)
async def change_member_role(
    workspace_id: uuid.UUID,
    member_user_id: uuid.UUID,
    body: MemberRoleUpdate,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    await workspace_service.require_membership(
        session, workspace_id, user.id, permission="members.manage"
    )
    member = await workspace_service.update_member_role(
        session, workspace_id, member_user_id, body.role
    )
    await session.commit()

    target = await session.get(User, member_user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Could not find user")

    return MemberRead(
        id=member.id,
        user_id=target.id,
        email=target.email,
        display_name=_user_display_name(target),
        role=member.role,
        joined_at=member.joined_at,
    )


@router.get("/{workspace_id}/stats")
async def workspace_stats(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """KPIs surfaced on the settings page (members / accounts / transactions)."""
    await workspace_service.require_membership(session, workspace_id, user.id)
    return await workspace_service.get_workspace_stats(session, workspace_id)


@router.post("/{workspace_id}/archive", response_model=WorkspaceRead)
async def archive_workspace_endpoint(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Soft-delete: flips is_archived. Requires owner role. Refuses to
    archive the requester's last accessible workspace."""
    await workspace_service.require_membership(
        session, workspace_id, user.id, permission="workspace.manage"
    )
    workspace = await workspace_service.archive_workspace(session, workspace_id, user.id)
    await session.commit()
    return _workspace_read(workspace, "owner")


@router.post("/{workspace_id}/setup", response_model=WorkspaceRead)
async def business_setup(
    workspace_id: uuid.UUID,
    body: WorkspaceSetup,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Business onboarding wizard — saves company info (legal name, address, CNPJ).

    Idempotent: repeated calls update existing values. Requires workspace.manage
    permission. Available for any workspace kind — the frontend only shows the
    wizard for business workspaces.
    """
    await workspace_service.require_membership(
        session, workspace_id, user.id, permission="workspace.manage"
    )
    result = await session.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.is_archived.is_(False))
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    if body.legal_name is not None:
        workspace.legal_name = body.legal_name.strip() or None
    if body.address is not None:
        workspace.address = body.address.strip() or None

    if body.tax_id is not None:
        # Upsert CNPJ into workspace_tax_ids
        existing_tax = await session.execute(
            select(WorkspaceTaxId).where(
                WorkspaceTaxId.workspace_id == workspace_id,
                WorkspaceTaxId.kind == "cnpj",
            )
        )
        tax_row = existing_tax.scalar_one_or_none()
        value = body.tax_id.strip()
        if value:
            if tax_row:
                tax_row.value = value
            else:
                session.add(WorkspaceTaxId(workspace_id=workspace_id, kind="cnpj", value=value))
        elif tax_row:
            await session.delete(tax_row)

    await session.commit()
    await session.refresh(workspace)
    return _workspace_read(workspace, "owner")


# ---------------------------------------------------------------------------
# Workspace logo (G2 — branding for PDF reports)
# ---------------------------------------------------------------------------

_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB


@router.post("/{workspace_id}/logo")
async def upload_workspace_logo(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Upload a workspace logo for branded reports. Accepts PNG, JPEG, WebP, GIF up to 2 MB."""
    await workspace_service.require_membership(
        session, workspace_id, user.id, permission="workspace.manage"
    )
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")

    data, content_type = await validate_upload(file, category="logo")

    # Normalise to PNG (strips EXIF, bounds dimensions)
    from app.services.invoice_logo_service import normalise

    try:
        png = normalise(data, content_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Store and record the key on the workspace
    from app.providers import get_storage_provider

    key = f"{workspace_id}/branding/logo.png"
    storage = get_storage_provider()
    await storage.upload(key, png, "image/png")
    workspace.logo_storage_key = key
    await session.commit()
    return {"detail": "Logo uploaded", "storage_key": key}


@router.get("/{workspace_id}/logo")
async def download_workspace_logo(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Download the workspace logo. Any member can read."""
    await workspace_service.require_membership(session, workspace_id, user.id)
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None or not workspace.logo_storage_key:
        raise HTTPException(status_code=404, detail="No logo")

    from app.providers import get_storage_provider

    storage = get_storage_provider()
    try:
        data = await storage.download(workspace.logo_storage_key)
    except Exception:
        raise HTTPException(status_code=404, detail="Logo file not found")
    return Response(content=data, media_type="image/png")


@router.delete("/{workspace_id}/logo", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace_logo(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    """Remove the workspace logo. Leaves the file for previously generated documents."""
    await workspace_service.require_membership(
        session, workspace_id, user.id, permission="workspace.manage"
    )
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    workspace.logo_storage_key = None
    await session.commit()
    return None


@router.delete(
    "/{workspace_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_workspace_member(
    workspace_id: uuid.UUID,
    member_user_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user),
):
    # Whoever manages members can remove anyone; anyone else can remove themselves only.
    requester = await workspace_service.require_membership(session, workspace_id, user.id)
    if member_user_id != user.id and "members.manage" not in await role_service.permissions_of(
        session, workspace_id, requester.role
    ):
        raise HTTPException(status_code=403, detail="Only someone who manages members can remove others")
    await workspace_service.remove_member(session, workspace_id, member_user_id)
    await session.commit()
    return None
