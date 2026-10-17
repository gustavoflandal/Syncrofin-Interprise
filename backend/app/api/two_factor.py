import json
import uuid
from datetime import datetime
from typing import Optional

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.services.crypto import decrypt, encrypt
from app.core.auth import current_active_user
from app.models.user_session import UserSession
from app.services import login_guard, mfa_policy, session_service
from app.core.auth_policy import require_local_auth_enabled
from app.core.database import get_async_session
from app.core.rate_limit import login_rate_limit
from app.core.redis import get_redis
from app.models.user import User
from app.schemas.two_factor import (
    TwoFactorDisableRequest,
    TwoFactorEnableRequest,
    TwoFactorSetupResponse,
    TwoFactorVerifyRequest,
)

router = APIRouter()
TOTP_VALID_WINDOW = 1


def _totp_secret(user: User) -> str | None:
    """Return the TOTP seed for ``user``, preferring the encrypted column with fallback to plaintext."""
    if user.totp_secret_enc:
        return decrypt(user.totp_secret_enc)
    return user.totp_secret


def _verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=TOTP_VALID_WINDOW)


def _parse_temp_token_payload(raw: str | bytes) -> dict[str, object] | None:
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        # Backward compatibility with existing temp tokens that only stored user_id.
        return {"user_id": raw, "available_methods": ["totp"]}
    if not isinstance(payload, dict) or not isinstance(payload.get("user_id"), str):
        return None
    return payload


@router.post(
    "/2fa/setup",
    response_model=TwoFactorSetupResponse,
    dependencies=[Depends(require_local_auth_enabled)],
)
async def setup_2fa(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    secret = pyotp.random_base32()
    user.totp_secret_enc = encrypt(secret)
    user.totp_secret = None
    session.add(user)
    await session.commit()

    totp = pyotp.TOTP(secret)
    otpauth_uri = totp.provisioning_uri(name=user.email, issuer_name="SyncroFin")

    return TwoFactorSetupResponse(secret=secret, otpauth_uri=otpauth_uri)


@router.post("/2fa/enable", dependencies=[Depends(require_local_auth_enabled)])
async def enable_2fa(
    body: TwoFactorEnableRequest,
    request: Request,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    secret = _totp_secret(user)
    if not secret:
        raise HTTPException(status_code=400, detail="Call /2fa/setup first")

    if not _verify_totp(secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid 2FA code")

    user.is_2fa_enabled = True
    session.add(user)
    await session.commit()
    # The first code just typed shows this person holds the device: this session may now go on.
    await session_service.mark_mfa_verified(session, session_service.session_id_from_request(request))
    return {"detail": "2FA enabled"}


class MfaStatusRead(BaseModel):
    applies: bool
    enforced: bool
    blocked: bool
    reminder: bool
    session_verified: bool
    enrolled: bool
    enforced_from: Optional[datetime] = None
    from_environment: bool


@router.get("/mfa-status", response_model=MfaStatusRead)
async def mfa_status(
    request: Request,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    """Where this person stands with the instance's second-factor rule (drives the enrolment screen)."""
    sid = session_service.session_id_from_request(request)
    row = await session.get(UserSession, sid) if sid else None
    status = mfa_policy.status_for(await mfa_policy.load_policy(session), user, bool(row and row.mfa_verified))
    return MfaStatusRead(
        applies=status.applies,
        enforced=status.enforced,
        blocked=status.blocked,
        reminder=status.reminder,
        session_verified=status.session_verified,
        enrolled=status.enrolled,
        enforced_from=status.enforced_from,
        from_environment=status.from_environment,
    )


@router.post("/2fa/disable", dependencies=[Depends(login_rate_limit)])
async def disable_2fa(
    body: TwoFactorDisableRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    from fastapi_users.db import SQLAlchemyUserDatabase
    from fastapi.security import OAuth2PasswordRequestForm

    # Verify password by authenticating
    user_db = SQLAlchemyUserDatabase(session, User)
    from app.core.auth import UserManager
    user_manager = UserManager(user_db)

    # Disabling the second factor is a password check like any other: it is limited by the lock, and every
    # miss counts, so a stolen session cannot be used to guess the password here.
    if login_guard.is_locked(user):
        raise HTTPException(status_code=400, detail="Invalid password")
    creds = OAuth2PasswordRequestForm(username=user.email, password=body.password)
    authenticated = await user_manager.authenticate(creds)
    if authenticated is None:
        await login_guard.password_failed(session, user)
        raise HTTPException(status_code=400, detail="Invalid password")

    # Verify TOTP code
    secret = _totp_secret(user)
    if not secret:
        raise HTTPException(status_code=400, detail="2FA is not set up")

    if not _verify_totp(secret, body.code):
        await login_guard.second_factor_failed(session, user)
        raise HTTPException(status_code=400, detail="Invalid 2FA code")

    user.totp_secret = None
    user.totp_secret_enc = None
    user.is_2fa_enabled = False
    session.add(user)
    await session.commit()
    return {"detail": "2FA disabled"}


@router.post("/2fa/verify", dependencies=[Depends(login_rate_limit)])
async def verify_2fa(
    body: TwoFactorVerifyRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_async_session),
):
    r = await get_redis()
    redis_key = f"2fa_temp:{body.temp_token}"
    raw_payload = await r.get(redis_key)

    if not raw_payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    payload = _parse_temp_token_payload(raw_payload)
    available_methods = payload.get("available_methods", []) if payload else []
    if payload is None or not isinstance(available_methods, list) or "totp" not in available_methods:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Load user
    result = await session.execute(select(User).where(User.id == uuid.UUID(str(payload["user_id"]))))
    user = result.scalar_one_or_none()
    secret = _totp_secret(user) if user else None
    if not user or not (user.is_2fa_enabled and secret):
        raise HTTPException(status_code=401, detail="Invalid token")

    # A locked account takes no codes, right or wrong (see services/login_guard.py).
    if login_guard.is_locked(user):
        raise HTTPException(status_code=401, detail="Invalid token")

    # Verify TOTP
    if not _verify_totp(secret, body.code):  # type: ignore[arg-type]
        await login_guard.second_factor_failed(session, user)
        raise HTTPException(status_code=400, detail="Invalid 2FA code")

    # Delete temp token
    await r.delete(redis_key)

    return await session_service.sign_in(session, user, request, response, "2fa")
