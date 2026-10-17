"""SCIM 2.0 (RFC 7644) — User provisioning endpoint.

Implements the minimum SCIM surface an IdP needs to push user lifecycle
events: list, get, create, replace, patch and deactivate.  Groups are not
covered (workspace membership is managed inside SyncroFin).

Authentication is a simple Bearer token checked against
``SCIM_BEARER_TOKEN`` — deliberately outside the session/JWT system.
"""
from __future__ import annotations

import logging
import re
import secrets
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi_users import schemas
from fastapi_users.exceptions import UserAlreadyExists
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import UserManager, get_user_manager
from app.core.config import get_settings
from app.core.database import get_async_session
from app.models.account import Account
from app.models.user import User
from app.models.workspace import WORKSPACE_ROLES, Workspace, WorkspaceMember
from app.services.category_service import create_default_categories
from app.services.rule_service import create_default_rules
from app.services.workspace_service import create_personal_workspace_for_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scim/v2", tags=["scim"])

_email_adapter = TypeAdapter(EmailStr)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def _require_scim_token(authorization: str = Header(...)) -> None:
    """Validate the SCIM bearer token.

    This is intentionally NOT the normal session/JWT auth: SCIM is a
    server-to-server protocol with its own credential.
    """
    settings = get_settings()
    if not settings.scim_enabled:
        raise HTTPException(status_code=404, detail="SCIM provisioning is not enabled")
    expected = settings.scim_bearer_token.get_secret_value()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="SCIM_BEARER_TOKEN is not configured",
        )
    parts = authorization.split(" ", 1)
    if (
        len(parts) != 2
        or parts[0].lower() != "bearer"
        or not secrets.compare_digest(parts[1].encode(), expected.encode())
    ):
        raise HTTPException(status_code=401, detail="Invalid SCIM bearer token")


# ---------------------------------------------------------------------------
# SCIM resource helpers
# ---------------------------------------------------------------------------

def _user_to_scim(user: User) -> dict[str, Any]:
    """Format a User as a SCIM 2.0 User resource."""
    prefs = user.preferences or {}
    display_name = prefs.get("display_name", "")
    parts = display_name.rsplit(" ", 1) if display_name else ["", ""]
    given = parts[0] if len(parts) > 1 else display_name
    family = parts[1] if len(parts) > 1 else ""

    created = ""
    # User model doesn't have created_at, use a fallback
    meta_created = getattr(user, "created_at", None)
    if meta_created and isinstance(meta_created, datetime):
        created = meta_created.isoformat()

    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": str(user.id),
        "userName": user.email,
        "name": {
            "givenName": given,
            "familyName": family,
        },
        "emails": [{"value": user.email, "primary": True}],
        "active": user.is_active,
        "externalId": user.scim_external_id or "",
        "meta": {
            "resourceType": "User",
            "created": created,
            "lastModified": created,
        },
    }


def _scim_list_response(users: list[User], total: int, start: int = 1) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": total,
        "startIndex": start,
        "itemsPerPage": len(users),
        "Resources": [_user_to_scim(u) for u in users],
    }


def _normalize_email(raw: str) -> str:
    try:
        return str(_email_adapter.validate_python(raw)).lower()
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="userName must be a valid e-mail") from exc


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/Users", dependencies=[Depends(_require_scim_token)])
async def scim_list_users(
    filter: str | None = Query(None),
    startIndex: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=1000),
    session: AsyncSession = Depends(get_async_session),
):
    """List or filter users."""
    query = select(User)

    # Basic filter support: userName eq "email"
    if filter:
        match = re.match(r'userName\s+eq\s+"([^"]+)"', filter, re.IGNORECASE)
        if match:
            email_filter = match.group(1).lower()
            query = query.where(func.lower(User.email) == email_filter)

    total_q = select(func.count()).select_from(query.subquery())
    total = await session.scalar(total_q) or 0

    users_result = await session.execute(
        query.order_by(User.email).offset(startIndex - 1).limit(count)
    )
    users = list(users_result.scalars().all())
    return _scim_list_response(users, total, startIndex)


@router.get("/Users/{user_id}", dependencies=[Depends(_require_scim_token)])
async def scim_get_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Get a single user."""
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_scim(user)


@router.post("/Users", dependencies=[Depends(_require_scim_token)], status_code=201)
async def scim_create_user(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Create a user from a SCIM payload."""
    body = await request.json()
    settings = get_settings()

    username = body.get("userName", "")
    external_id = body.get("externalId", "")
    name_data = body.get("name") or {}
    active = body.get("active", True)

    if not username:
        raise HTTPException(status_code=400, detail="userName is required")

    email = _normalize_email(username)

    # Idempotency: if externalId matches, return existing user
    if external_id:
        existing = await session.execute(
            select(User).where(User.scim_external_id == external_id)
        )
        user = existing.scalar_one_or_none()
        if user is not None:
            return _user_to_scim(user)

    # Check if user exists by email
    existing = await session.execute(
        select(User).where(func.lower(User.email) == email)
    )
    user = existing.scalar_one_or_none()
    if user is not None:
        # Update SCIM external ID
        if external_id:
            user.scim_external_id = external_id
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return _user_to_scim(user)

    # Create new user
    given = name_data.get("givenName", "")
    family = name_data.get("familyName", "")
    display_name = f"{given} {family}".strip() or email.split("@", 1)[0]

    preferences = {
        "language": "en",
        "date_format": "MM/DD/YYYY",
        "timezone": "UTC",
        "currency_display": settings.default_currency,
        "display_name": display_name,
        "auth_provider": "SCIM",
    }

    user_create = schemas.BaseUserCreate(
        email=email,
        password=secrets.token_urlsafe(32),
        is_verified=True,
        is_active=bool(active) if settings.scim_auto_activate else False,
    )
    try:
        user = await user_manager.create(user_create, safe=True, request=None)
    except UserAlreadyExists:
        user = (
            await session.execute(select(User).where(func.lower(User.email) == email))
        ).scalar_one()

    db_session = user_manager.user_db.session
    await db_session.execute(
        sql_update(User)
        .where(User.id == user.id)
        .values(
            preferences=preferences,
            scim_external_id=external_id or None,
            is_active=bool(active) if settings.scim_auto_activate else False,
        )
    )
    await db_session.refresh(user)

    workspace = await create_personal_workspace_for_user(db_session, user)
    wallet = Account(
        user_id=user.id,
        workspace_id=workspace.id,
        name="Wallet",
        type="checking",
        balance=0,
        currency=settings.default_currency,
    )
    db_session.add(wallet)
    await db_session.commit()
    await create_default_categories(db_session, user.id, "en", workspace_id=workspace.id)
    await create_default_rules(db_session, user.id, "en", workspace_id=workspace.id)
    await db_session.commit()

    # Add to default workspace if configured
    if settings.scim_default_workspace_id:
        try:
            ws_id = uuid.UUID(settings.scim_default_workspace_id)
            ws = await db_session.get(Workspace, ws_id)
            if ws is not None:
                role = ws.scim_default_role if ws.scim_default_role in WORKSPACE_ROLES else "editor"
                db_session.add(
                    WorkspaceMember(workspace_id=ws_id, user_id=user.id, role=role)
                )
                await db_session.commit()
        except Exception as exc:
            await db_session.rollback()
            logger.warning("SCIM: could not add user to default workspace: %s", exc)

    await db_session.refresh(user)
    return _user_to_scim(user)


@router.put("/Users/{user_id}", dependencies=[Depends(_require_scim_token)])
async def scim_replace_user(
    user_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Replace a user (full update)."""
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    body = await request.json()
    name_data = body.get("name") or {}
    active = body.get("active")
    external_id = body.get("externalId")

    given = name_data.get("givenName", "")
    family = name_data.get("familyName", "")
    display_name = f"{given} {family}".strip()

    if display_name:
        prefs = dict(user.preferences or {})
        prefs["display_name"] = display_name
        user.preferences = prefs

    if active is not None:
        user.is_active = bool(active)

    if external_id is not None:
        user.scim_external_id = external_id or None

    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _user_to_scim(user)


@router.patch("/Users/{user_id}", dependencies=[Depends(_require_scim_token)])
async def scim_patch_user(
    user_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    """Partial update (SCIM PatchOp). Typically used for deactivation."""
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    body = await request.json()
    operations = body.get("Operations", body.get("operations", []))

    for op in operations:
        if str(op.get("op", "")).lower() != "replace":
            continue
        path = op.get("path", "")
        value = op.get("value")

        if path == "active":
            # Some IdPs (Azure AD) send the string "False" instead of a boolean.
            user.is_active = value.lower() == "true" if isinstance(value, str) else bool(value)
        elif path == "name" and isinstance(value, dict):
            _set_display_name(user, value)
        elif not path and isinstance(value, dict):
            if "active" in value:
                user.is_active = bool(value["active"])
            if isinstance(value.get("name"), dict):
                _set_display_name(user, value["name"])

    session.add(user)
    await session.commit()
    await session.refresh(user)
    return _user_to_scim(user)


def _set_display_name(user: User, name: dict[str, Any]) -> None:
    display = f"{name.get('givenName', '')} {name.get('familyName', '')}".strip()
    if display:
        prefs = dict(user.preferences or {})
        prefs["display_name"] = display
        user.preferences = prefs


@router.delete("/Users/{user_id}", dependencies=[Depends(_require_scim_token)], status_code=204)
async def scim_delete_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
):
    """Deactivate a user (soft-delete). SCIM DELETE does not hard-delete."""
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    session.add(user)
    await session.commit()
    return Response(status_code=204)
