import uuid
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import password_policy
from app.core.auth import UserManager, current_active_user, current_superuser, get_user_manager
from app.core.auth_policy import require_local_auth_enabled
from app.core.database import get_async_session
from app.models.user import User
from app.models.user_session import UserSession
from app.schemas.admin import (
    AdminUserCreate,
    AdminUserList,
    AdminUserRead,
    AdminUserUpdate,
    AppSettingRead,
    AppSettingUpdate,
)
from app.services import admin_service, login_guard, mfa_policy, session_service

router = APIRouter(prefix="/api/admin", tags=["admin"])

ALLOWED_SETTINGS = {
    "registration_enabled",
    "credit_card_accounting_mode",
    "use_provider_categories",
    "theme_color_light",
    "theme_color_dark",
    "number_format",
    "date_format",
    # Second-factor policy (services/mfa_policy.py).
    "mfa_required",
    "mfa_required_scope",
    "mfa_grace_days",
}


@router.get("/users", response_model=AdminUserList)
async def list_users(
    search: str = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(current_superuser),
):
    users, total = await admin_service.list_users(session, search, page, limit)
    return AdminUserList(
        items=[AdminUserRead.model_validate(u) for u in users],
        total=total,
    )


@router.post(
    "/users",
    response_model=AdminUserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_local_auth_enabled)],
)
async def create_user(
    data: AdminUserCreate,
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(current_superuser),
    user_manager: UserManager = Depends(get_user_manager),
):
    try:
        user = await admin_service.create_user(session, user_manager, data)
    except password_policy.PasswordRejected as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=password_policy.http_detail(e.reason))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return AdminUserRead.model_validate(user)


@router.get("/users/{user_id}", response_model=AdminUserRead)
async def get_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(current_superuser),
):
    user = await admin_service.get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AdminUserRead.model_validate(user)


@router.patch("/users/{user_id}", response_model=AdminUserRead)
async def update_user(
    user_id: uuid.UUID,
    data: AdminUserUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    if data.password is not None:
        require_local_auth_enabled()
    try:
        user = await admin_service.update_user(session, user_id, data, current_user.id)
    except password_policy.PasswordRejected as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=password_policy.http_detail(e.reason))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return AdminUserRead.model_validate(user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    try:
        deleted = await admin_service.delete_user(session, user_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@router.get("/settings/{key}", response_model=AppSettingRead)
async def get_setting(
    key: str,
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(current_superuser),
):
    setting = await admin_service.get_app_setting(session, key)
    if not setting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setting not found")
    return AppSettingRead.model_validate(setting)


@router.patch("/settings/{key}", response_model=AppSettingRead)
async def update_setting(
    key: str,
    data: AppSettingUpdate,
    request: Request,
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(current_superuser),
):
    if key not in ALLOWED_SETTINGS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Setting '{key}' is not configurable",
        )
    SETTING_VALIDATORS = {
        "registration_enabled": {"true", "false"},
        "credit_card_accounting_mode": {"cash", "accrual"},
        "use_provider_categories": {"true", "false"},
        "number_format": {"auto", "comma_dot", "dot_comma", "space_comma"},
        "date_format": {"auto", "dmy", "mdy", "ymd"},
        "mfa_required": {"true", "false"},
        "mfa_required_scope": set(mfa_policy.SCOPES),
    }

    if key == "mfa_grace_days" and not (
        data.value.isdigit() and 0 <= int(data.value) <= mfa_policy.MAX_GRACE_DAYS
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid value for '{key}'. Allowed: 0 to {mfa_policy.MAX_GRACE_DAYS} days",
        )

    if key in SETTING_VALIDATORS and data.value not in SETTING_VALIDATORS[key]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid value for '{key}'. Allowed: {SETTING_VALIDATORS[key]}",
        )

    if key in ("theme_color_light", "theme_color_dark"):
        if not re.match(r"^#[0-9A-Fa-f]{6}$", data.value):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid hex color code for '{key}'. Expected format: #RRGGBB",
            )

    if key == "mfa_required":
        # Turning the rule on starts the grace period; turning it off forgets it.
        before = await mfa_policy.load_policy(session)
        if data.value == "true" and not before.required:
            # The person turning it on must hold a second factor themselves, or the next request
            # would already be held back and nobody could turn it off again from the panel.
            sid = session_service.session_id_from_request(request)
            row = await session.get(UserSession, sid) if sid else None
            if row is None or not row.mfa_verified:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="MFA_ADMIN_NOT_ENROLLED",
                )
            grace = before.grace_days
            enforced_from = mfa_policy.enforcement_date(grace)
            await admin_service.set_app_setting(session, "mfa_enforced_from", enforced_from.isoformat())
        elif data.value == "false":
            await admin_service.set_app_setting(session, "mfa_enforced_from", "")

    setting = await admin_service.set_app_setting(session, key, data.value)
    return AppSettingRead.model_validate(setting)


class MfaPolicyRead(BaseModel):
    required: bool
    scope: str
    grace_days: int
    #: When enforcement starts (or started); null when it applies at once.
    enforced_from: Optional[datetime] = None
    #: `REQUIRE_MFA` is set in the environment: the panel cannot lift it.
    from_environment: bool
    users_total: int
    users_without_2fa: int


@router.get("/mfa-policy", response_model=MfaPolicyRead)
async def mfa_policy_overview(
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(current_superuser),
):
    """The rule and how many accounts it would hold back (the ones with no authenticator app)."""
    policy = await mfa_policy.load_policy(session)
    total = (await session.execute(select(func.count()).select_from(User).where(User.is_active.is_(True)))).scalar_one()
    without = (
        await session.execute(
            select(func.count()).select_from(User).where(
                User.is_active.is_(True), User.is_2fa_enabled.is_(False)
            )
        )
    ).scalar_one()
    return MfaPolicyRead(
        required=policy.required,
        scope=policy.scope,
        grace_days=policy.grace_days,
        enforced_from=policy.enforced_from,
        from_environment=policy.from_environment,
        users_total=total,
        users_without_2fa=without,
    )


@router.post("/users/{user_id}/reset-2fa", status_code=status.HTTP_204_NO_CONTENT)
async def reset_user_two_factor(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Remove someone's authenticator app and end their sessions: for a lost phone.

    They sign in with the password, and, if the instance requires a second factor, are asked to
    enrol a new one. Administrators use the normal "disable 2FA" flow for themselves.
    """
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use the 2FA settings for your own account")
    user = await admin_service.get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.totp_secret = None
    user.totp_secret_enc = None
    user.is_2fa_enabled = False
    session.add(user)
    await session_service.revoke_all(session, user.id, "2fa_reset")
    await session.commit()


@router.post("/users/{user_id}/unlock", status_code=status.HTTP_204_NO_CONTENT)
async def unlock_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(current_superuser),
):
    """Lift the pause on an account locked by wrong passwords, without waiting for it to end."""
    user = await admin_service.get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await login_guard.unlock(session, user.id, reason="admin")
    await session.commit()


@router.get("/registration-status")
async def registration_status(
    session: AsyncSession = Depends(get_async_session),
):
    enabled = await admin_service.is_registration_enabled(session)
    return {"enabled": enabled}


@router.get("/default-colors")
async def default_colors(
    session: AsyncSession = Depends(get_async_session),
):
    light = await admin_service.get_app_setting(session, "theme_color_light")
    dark = await admin_service.get_app_setting(session, "theme_color_dark")
    return {"light": light.value if light else None, "dark": dark.value if dark else None}


@router.get("/accounting-mode")
async def accounting_mode(
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(current_active_user),
):
    mode = await admin_service.get_credit_card_accounting_mode(session)
    return {"mode": mode}


@router.get("/number-format")
async def number_format(
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(current_active_user),
):
    """Global display format for numbers and dates. Readable by any signed-in
    user (not just admins) so the frontend can format consistently for everyone.
    Defaults to 'auto' — derive separators from each user's display currency."""
    fmt = await admin_service.get_number_format(session)
    return {"format": fmt}


@router.get("/date-format")
async def date_format(
    session: AsyncSession = Depends(get_async_session),
    _user: User = Depends(current_active_user),
):
    """Global display format for dates. Readable by any signed-in user.
    Defaults to 'auto' — derive the field order from the number format /
    display currency. Month names always follow the user's app language."""
    fmt = await admin_service.get_date_format(session)
    return {"format": fmt}


async def check_registration_enabled(
    request: Request,
    session: AsyncSession = Depends(get_async_session),
):
    enabled = await admin_service.is_registration_enabled(session)
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is currently disabled",
        )
