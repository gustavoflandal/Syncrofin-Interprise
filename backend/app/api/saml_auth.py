"""SAML 2.0 SSO — Service Provider endpoints.

Mirrors the OIDC flow in ``oidc_auth.py``: an unauthenticated redirect to
the IdP, a signed assertion back, and the same get-or-create-user logic
that links by (saml_idp_entity_id, saml_name_id), falls back to e-mail,
and auto-registers when allowed.

python3-saml (``onelogin.saml2``) handles the XML; if the library is not
installed (it requires the ``xmlsec1`` system library), the endpoints return
503 with a clear message so the rest of the application is unaffected.
"""
from __future__ import annotations

import json
import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi_users import schemas
from fastapi_users.exceptions import UserAlreadyExists
from pydantic import BaseModel, EmailStr, TypeAdapter, ValidationError
from sqlalchemy import func, select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import UserManager, get_user_manager
from app.core.config import get_settings
from app.core.database import get_async_session
from app.core.redis import get_redis
from app.models.account import Account
from app.models.user import User
from app.models.workspace import WORKSPACE_ROLES, Workspace, WorkspaceMember
from app.services import admin_service, session_service
from app.services.category_service import create_default_categories
from app.services.rule_service import create_default_rules
from app.services.workspace_service import create_personal_workspace_for_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/saml", tags=["auth"])

SAML_STATE_TTL = 600  # seconds

# ---------------------------------------------------------------------------
# python3-saml availability
# ---------------------------------------------------------------------------
try:
    from onelogin.saml2.auth import OneLogin_Saml2_Auth  # type: ignore[import-untyped]
    from onelogin.saml2.idp_metadata_parser import (  # type: ignore[import-untyped]
        OneLogin_Saml2_IdPMetadataParser,
    )

    _SAML_AVAILABLE = True
except ImportError:
    _SAML_AVAILABLE = False


def _require_saml_lib() -> None:
    if not _SAML_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail=(
                "python3-saml is not installed (it needs the xmlsec1 system library). "
                "Install it to enable SAML SSO."
            ),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class SAMLConfigResponse(BaseModel):
    enabled: bool
    provider_name: str = "SAML"
    local_auth_enabled: bool = True


_email_adapter = TypeAdapter(EmailStr)


def _normalize_email(raw: str) -> str:
    try:
        return str(_email_adapter.validate_python(raw)).lower()
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail="Invalid e-mail in SAML assertion") from exc


def _require_enabled() -> None:
    # Config gate first so a disabled instance answers 404 even without the library.
    if not get_settings().saml_login_available:
        raise HTTPException(status_code=404, detail="SAML SSO is not enabled")
    _require_saml_lib()


async def _prepare_saml_request(request: Request) -> dict[str, Any]:
    """Build the dict that python3-saml's ``OneLogin_Saml2_Auth`` expects."""
    settings = get_settings()

    # Derive SP URLs from the running server (behind a proxy, trust the forwarded headers).
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost"))

    sp_entity_id = settings.saml_sp_entity_id or f"{scheme}://{host}/api/auth/saml/metadata"
    acs_url = f"{scheme}://{host}/api/auth/saml/acs"
    sls_url = f"{scheme}://{host}/api/auth/saml/slo"

    # Build IdP settings from metadata URL
    idp_settings: dict[str, Any] = {}
    if settings.saml_idp_metadata_url:
        try:
            idp_data = OneLogin_Saml2_IdPMetadataParser.parse_remote(
                settings.saml_idp_metadata_url, timeout=10
            )
            idp_settings = idp_data.get("idp", {})
        except Exception as exc:
            logger.warning("Failed to fetch SAML IdP metadata: %s", exc)
            raise HTTPException(
                status_code=502, detail="Could not fetch SAML IdP metadata"
            ) from exc

    saml_settings: dict[str, Any] = {
        "strict": True,
        "debug": settings.debug,
        "sp": {
            "entityId": sp_entity_id,
            "assertionConsumerService": {
                "url": acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "singleLogoutService": {
                "url": sls_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "NameIDFormat": settings.saml_name_id_format,
        },
        "idp": idp_settings,
    }

    # SP certificate and key (optional but recommended for signed requests)
    if settings.saml_sp_cert:
        saml_settings["sp"]["x509cert"] = settings.saml_sp_cert
    if settings.saml_sp_key.get_secret_value():
        saml_settings["sp"]["privateKey"] = settings.saml_sp_key.get_secret_value()

    return {
        "https": "on" if scheme == "https" else "off",
        "http_host": host,
        "script_name": str(request.url.path),
        "get_data": dict(request.query_params),
        "post_data": dict(await request.form()) if request.method == "POST" else {},
        "custom_base_path": "",
        # Settings travel with the request dict and are split off in _build_saml_auth.
        "_saml_settings": saml_settings,
    }


def _build_saml_auth(req_data: dict[str, Any]) -> Any:
    saml_settings = req_data.pop("_saml_settings")
    return OneLogin_Saml2_Auth(req_data, old_settings=saml_settings)


# ---------------------------------------------------------------------------
# Role sync (mirrors OIDC pattern)
# ---------------------------------------------------------------------------

def _provider_roles(attributes: dict[str, Any]) -> set[str]:
    raw_roles = attributes.get(get_settings().saml_roles_attribute, [])
    if isinstance(raw_roles, str):
        return {raw_roles}
    if isinstance(raw_roles, (list, tuple, set)):
        return {str(r) for r in raw_roles}
    return set()


def _parse_workspace_role_map(raw: str) -> dict[str, str]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=500, detail="SAML_WORKSPACE_ROLE_MAP must be valid JSON"
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=500, detail="SAML_WORKSPACE_ROLE_MAP must be a JSON object"
        )
    role_map = {str(k): str(v).lower() for k, v in parsed.items()}
    invalid = sorted({role for role in role_map.values() if role not in WORKSPACE_ROLES})
    if invalid:
        raise HTTPException(
            status_code=500,
            detail=f"SAML_WORKSPACE_ROLE_MAP contains invalid roles: {', '.join(invalid)}",
        )
    return role_map


def _desired_workspace_role(provider_roles: set[str], role_map: dict[str, str]) -> str | None:
    role_rank = {"viewer": 1, "editor": 2, "owner": 3}
    matches = [role_map[role] for role in provider_roles if role in role_map]
    if not matches:
        return None
    return max(matches, key=lambda role: role_rank[role])


async def _sync_saml_roles(
    user: User, attributes: dict[str, Any], session: AsyncSession
) -> None:
    settings = get_settings()
    if not settings.saml_sync_roles:
        return

    provider_roles = _provider_roles(attributes)

    admin_roles = {r.strip() for r in settings.saml_admin_roles.split(",") if r.strip()}
    if admin_roles:
        user.is_superuser = bool(provider_roles & admin_roles)
        session.add(user)

    role_map = _parse_workspace_role_map(settings.saml_workspace_role_map)
    desired_role = _desired_workspace_role(provider_roles, role_map)
    if desired_role is None:
        return

    workspace_result = await session.execute(
        select(Workspace)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(
            WorkspaceMember.user_id == user.id,
            Workspace.kind == "personal",
            Workspace.created_by_user_id == user.id,
        )
        .limit(1)
    )
    workspace = workspace_result.scalar_one_or_none()
    if workspace is None:
        return
    member_result = await session.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    member = member_result.scalar_one_or_none()
    if member is not None and member.role != desired_role:
        # The owner of a personal workspace is never demoted by the IdP.
        if workspace.kind == "personal" and member.role == "owner" and desired_role != "owner":
            return
        member.role = desired_role
        session.add(member)


# ---------------------------------------------------------------------------
# Get or create user (mirrors OIDC)
# ---------------------------------------------------------------------------

def _first(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    return str(value) if value else ""


async def _get_or_create_saml_user(
    name_id: str,
    attributes: dict[str, Any],
    idp_entity_id: str,
    session: AsyncSession,
    user_manager: UserManager,
) -> User:
    settings = get_settings()

    # 1. Lookup by SAML identity
    linked = await session.execute(
        select(User).where(
            User.saml_idp_entity_id == idp_entity_id,
            User.saml_name_id == name_id,
        )
    )
    user = linked.scalar_one_or_none()
    if user is not None:
        await _sync_saml_roles(user, attributes, session)
        await session.commit()
        await session.refresh(user)
        return user

    # 2. Determine email
    email_attr = _first(
        attributes.get("email")
        or attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress")
    )
    if not email_attr:
        # Fall back to NameID if it looks like an email
        if "@" in name_id:
            email_attr = name_id
        else:
            raise HTTPException(
                status_code=400, detail="SAML assertion did not contain an email"
            )
    email = _normalize_email(email_attr)

    # 3. Lookup by email
    existing = await session.execute(
        select(User).where(func.lower(User.email) == email)
    )
    user = existing.scalar_one_or_none()
    if user is not None:
        # Link existing user to SAML identity
        if user.saml_idp_entity_id and user.saml_name_id:
            raise HTTPException(
                status_code=403, detail="SAML identity is linked to a different account"
            )
        user.saml_idp_entity_id = idp_entity_id
        user.saml_name_id = name_id
        session.add(user)
        await _sync_saml_roles(user, attributes, session)
        await session.commit()
        await session.refresh(user)
        return user

    # 4. Auto-register
    if not await admin_service.is_registration_enabled(session):
        raise HTTPException(status_code=403, detail="Registration is disabled")
    if not settings.saml_auto_register:
        raise HTTPException(
            status_code=403,
            detail="No local account is linked to this SAML identity",
        )

    first_name = _first(
        attributes.get("firstName")
        or attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname")
    )
    last_name = _first(
        attributes.get("lastName")
        or attributes.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname")
    )
    display_name = f"{first_name} {last_name}".strip() or email.split("@", 1)[0]

    preferences = {
        "language": "en",
        "date_format": "MM/DD/YYYY",
        "timezone": "UTC",
        "currency_display": settings.default_currency,
        "display_name": display_name,
        "auth_provider": settings.saml_provider_name,
    }

    provider_roles = _provider_roles(attributes)
    admin_roles = {r.strip() for r in settings.saml_admin_roles.split(",") if r.strip()}

    user_create = schemas.BaseUserCreate(
        email=email,
        password=secrets.token_urlsafe(32),
        is_verified=True,
        is_superuser=bool(settings.saml_sync_roles and admin_roles and provider_roles & admin_roles),
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
            saml_idp_entity_id=idp_entity_id,
            saml_name_id=name_id,
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
    await _sync_saml_roles(user, attributes, db_session)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/config", response_model=SAMLConfigResponse)
async def saml_config():
    settings = get_settings()
    return SAMLConfigResponse(
        enabled=settings.saml_login_available,
        provider_name=settings.saml_provider_name or "SAML",
        local_auth_enabled=settings.local_auth_enabled,
    )


@router.get("/metadata")
async def saml_metadata(request: Request):
    """Return SP metadata XML for registering with the IdP."""
    _require_enabled()
    req_data = await _prepare_saml_request(request)
    auth = _build_saml_auth(req_data)
    saml_settings = auth.get_settings()
    metadata = saml_settings.get_sp_metadata()
    errors = saml_settings.validate_metadata(metadata)
    if errors:
        raise HTTPException(status_code=500, detail=f"SP metadata validation failed: {errors}")
    return Response(content=metadata, media_type="application/xml")


@router.get("/login")
async def saml_login(request: Request):
    """Redirect the browser to the IdP's SSO URL."""
    _require_enabled()
    req_data = await _prepare_saml_request(request)
    auth = _build_saml_auth(req_data)

    # Store a relay state so we can verify the response
    relay_state = secrets.token_urlsafe(32)
    r = await get_redis()
    await r.set(f"saml_state:{relay_state}", "1", ex=SAML_STATE_TTL)

    sso_url = auth.login(return_to=relay_state)
    return RedirectResponse(sso_url)


@router.post("/acs")
async def saml_acs(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
):
    """Assertion Consumer Service — receives the SAML response from the IdP."""
    _require_enabled()
    settings = get_settings()

    req_data = await _prepare_saml_request(request)
    auth = _build_saml_auth(req_data)
    auth.process_response()
    errors = auth.get_errors()
    if errors:
        logger.warning("SAML response validation errors: %s", errors)
        raise HTTPException(
            status_code=400,
            detail=f"SAML authentication failed: {', '.join(errors)}",
        )

    if not auth.is_authenticated():
        raise HTTPException(status_code=401, detail="SAML authentication failed")

    name_id = auth.get_nameid()
    attributes = auth.get_attributes()
    # The signature was validated against this IdP's metadata, so its entityId
    # is the trustworthy identifier for the (idp, name_id) pair.
    idp_entity_id = (
        auth.get_settings().get_idp_data().get("entityId") or settings.saml_idp_metadata_url
    )

    user = await _get_or_create_saml_user(
        name_id, attributes, idp_entity_id, session, user_manager
    )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    frontend_url = settings.frontend_url.rstrip("/")
    # 303 so the browser turns the IdP's POST into a GET on the frontend callback.
    redirect = RedirectResponse(f"{frontend_url}/auth/saml/callback", status_code=303)
    await session_service.sign_in_redirect(session, user, request, redirect, "saml")
    return redirect


@router.get("/slo")
async def saml_slo(request: Request):
    """Redirect to IdP Single Logout URL."""
    _require_enabled()
    req_data = await _prepare_saml_request(request)
    auth = _build_saml_auth(req_data)
    return RedirectResponse(auth.logout())
