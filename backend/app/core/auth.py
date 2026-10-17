import logging
import uuid
from decimal import Decimal
from typing import Optional, cast

from fastapi import Depends, HTTPException, Request
from fastapi_users import BaseUserManager, FastAPIUsers, InvalidPasswordException, UUIDIDMixin, schemas
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.jwt import generate_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_context import current_context, set_actor
from app.core.auth_policy import local_auth_enabled, require_local_auth_enabled
from app.core.config import get_settings
from app.core.database import get_async_session
from app.core import password_policy
from app.core.defaults import default_preferences
from app.models.user import User

settings = get_settings()
logger = logging.getLogger(__name__)

#: How long an invitation link stays valid. A reset link is short-lived because
#: someone is waiting at the keyboard; an invitation lands in an inbox that may
#: not be opened until next week.
INVITE_TOKEN_LIFETIME_SECONDS = 7 * 24 * 60 * 60


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    user_db: SQLAlchemyUserDatabase
    reset_password_token_secret = settings.secret_key
    verification_token_secret = settings.secret_key

    async def validate_password(self, password: str, user: schemas.UC | User) -> None:
        """Every way of choosing a password ends here (sign-up, reset, change, setup, an admin's edit)."""
        reason = password_policy.first_problem(password, email=getattr(user, "email", None))
        if reason is not None:
            raise InvalidPasswordException(reason=reason)

    async def create(
        self,
        user_create: schemas.UC,
        safe: bool = False,
        request: Request | None = None,
    ) -> User:
        """Fill in what the sign-up form did not send.

        The web form sends the language and the currency; the date format and the time zone are not on it. Without
        this they would be missing, and every screen would guess its own. What the person chose is kept; the rest
        is the product default (see app.core.defaults).
        """
        chosen = getattr(user_create, "preferences", None) or {}
        user_create = user_create.model_copy(
            update={"preferences": {**default_preferences(), **chosen}}
        )
        return await super().create(user_create, safe=safe, request=request)

    async def update(
        self,
        user_update: schemas.BaseUserUpdate,
        user: User,
        safe: bool = False,
        request: Request | None = None,
    ) -> User:
        if user_update.password is not None:
            require_local_auth_enabled()
        return await super().update(user_update, user, safe=safe, request=request)

    async def on_after_reset_password(self, user: User, request: Optional[Request] = None):
        """A reset means the old password may be in someone else's hands: end every session."""
        from app.services import session_service

        await session_service.revoke_all(self.user_db.session, user.id, "password_changed")
        # Whoever holds the reset link owns the mailbox: the lock has done its job.
        from app.services import login_guard

        await login_guard.unlock(self.user_db.session, user.id, reason="password_reset")
        await self.user_db.session.commit()

    async def on_after_update(
        self, user: User, update_dict: dict, request: Optional[Request] = None
    ):
        """Changing the password ends the *other* sessions; the one that changed it stays."""
        if "password" not in update_dict and "hashed_password" not in update_dict:
            return
        from app.services import session_service

        keep = session_service.session_id_from_request(request) if request is not None else None
        await session_service.revoke_all(self.user_db.session, user.id, "password_changed", except_id=keep)
        await self.user_db.session.commit()

    def issue_reset_token(self, user: User, lifetime_seconds: Optional[int] = None) -> str:
        """A password-reset token, built exactly as `forgot_password` builds it.

        The token carries a fingerprint of the current password hash, so it
        works once: the moment the password changes, the fingerprint no longer
        matches and every outstanding link for that account dies with it.
        """
        token_data = {
            "sub": str(user.id),
            "password_fgpt": self.password_helper.hash(user.hashed_password),
            "aud": self.reset_password_token_audience,
        }
        return generate_jwt(
            token_data,
            self.reset_password_token_secret,
            lifetime_seconds or self.reset_password_token_lifetime_seconds,
        )

    async def on_after_forgot_password(
        self, user: User, token: str, request: Optional[Request] = None
    ):
        """Deliver the reset link. Without this hook the token goes nowhere."""
        from app.services import email_service, email_templates

        if not local_auth_enabled():
            return
        link = email_service.frontend_link("/reset-password", token=token)
        subject, body = email_templates.password_reset(
            (user.preferences or {}).get("language"),
            link,
            self.reset_password_token_lifetime_seconds // 60,
        )
        # Background, so the endpoint answers at the same speed whether or not
        # the address exists (see `send_in_background`).
        email_service.send_in_background(user.email, subject, body)

    async def on_after_register(self, user: User, request: Optional[Request] = None):
        logger.info("User %s has registered.", user.id)
        # If request is None, this was called programmatically (e.g., from setup endpoint)
        # which handles wallet creation, categories, and rules itself.
        if request is None:
            return
        # Create default wallet for users registered via /auth/register.
        from app.models.account import Account
        from app.services.category_service import create_default_categories
        from app.services.rule_service import create_default_rules
        from app.services.workspace_service import create_personal_workspace_for_user

        session = self.user_db.session
        currency = user.primary_currency
        lang = (user.preferences or {}).get("language") or get_settings().default_language

        # Every new user gets a Personal workspace + owner membership.
        # All their seeded data (wallet, categories, rules) reparent to it.
        workspace = await create_personal_workspace_for_user(session, user)

        wallet_name = "Carteira" if lang.startswith("pt") else "Wallet"
        wallet = Account(
            user_id=user.id,
            workspace_id=workspace.id,
            name=wallet_name,
            type="checking",
            balance=Decimal("0.00"),
            currency=currency,
        )
        session.add(wallet)
        await session.commit()

        # Create default categories and rules for the new user
        await create_default_categories(session, user.id, lang, workspace_id=workspace.id)
        await create_default_rules(session, user.id, lang, workspace_id=workspace.id)


async def get_user_manager(user_db: SQLAlchemyUserDatabase = Depends(get_user_db)):
    yield UserManager(user_db)


bearer_transport = BearerTransport(tokenUrl="api/auth/login")


class SessionJWTStrategy(JWTStrategy):
    """Accepts an access token only while the session it names is alive.

    Every request looks the session up, so ending it (logout, "sign out that device", a password
    change) takes effect on the very next request. A token with no `sid`, from before sessions
    existed, is refused: whoever holds one signs in again once.
    """

    async def read_token(self, token: Optional[str], user_manager: BaseUserManager[User, uuid.UUID]) -> Optional[User]:
        from app.models.user_session import UserSession
        from app.services import api_token_service, session_service

        if api_token_service.looks_like_api_token(token):
            db_for_token: AsyncSession = cast(SQLAlchemyUserDatabase, user_manager.user_db).session
            found = await api_token_service.authenticate(db_for_token, cast(str, token))
            return found[1] if found else None

        claims = session_service.read_access_claims(token)
        if not claims or not claims.get("sid") or not claims.get("sub"):
            return None
        try:
            sid = uuid.UUID(claims["sid"])
            user_id = user_manager.parse_id(claims["sub"])
        except (ValueError, Exception):
            return None
        db: AsyncSession = cast(SQLAlchemyUserDatabase, user_manager.user_db).session
        row = await db.get(UserSession, sid)
        if row is None or row.user_id != user_id or not session_service.is_active(row):
            return None
        await session_service.touch(db, row)
        try:
            return await user_manager.get(user_id)
        except Exception:
            return None

    async def write_token(self, user: User) -> str:  # pragma: no cover - guard against misuse
        raise RuntimeError("Access tokens belong to a session: use session_service.sign_in")


def get_jwt_strategy() -> SessionJWTStrategy:
    return SessionJWTStrategy(
        secret=settings.secret_key.get_secret_value(),
        lifetime_seconds=settings.access_token_expire_minutes * 60,
    )


auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

_active_user = fastapi_users.current_user(active=True)
_superuser = fastapi_users.current_user(active=True, superuser=True)


async def _enforce_mfa(request: Request, user: User, db: AsyncSession) -> None:
    """While the instance requires a second factor, a session without one may only enrol."""
    from app.models.user_session import UserSession
    from app.services import mfa_policy, session_service

    policy = await mfa_policy.load_policy(db)
    if not (policy.applies_to(user) and policy.enforced()):
        return
    if mfa_policy.is_enrolment_route(request.method, request.url.path):
        return
    sid = session_service.session_id_from_request(request)
    row = await db.get(UserSession, sid) if sid else None
    if row is not None and not row.mfa_verified:
        raise HTTPException(status_code=403, detail="MFA_ENROLLMENT_REQUIRED")


async def current_principal(
    request: Request,
    user: User = Depends(_active_user),
    db: AsyncSession = Depends(get_async_session),
) -> User:
    """Whoever the request acts as: a signed-in person, or the person behind an API token.

    Tells the audit trail who is acting, and holds back a session that still owes the instance a second
    factor. Only the workspace's own routes use this directly (`current_workspace`); everything else
    goes through `current_active_user`, which refuses a token.
    """
    token = current_context().api_token_id is not None
    set_actor(user.id, "api_token" if token else "user")
    if not token:  # a token has no session to hold back, and is not signed in with a password
        await _enforce_mfa(request, user, db)
    return user


def _refuse_api_token() -> None:
    if current_context().api_token_id is not None:
        raise HTTPException(status_code=403, detail="API_TOKEN_NOT_ALLOWED")


async def current_active_user(user: User = Depends(current_principal)) -> User:
    """The signed-in person. A route that acts on the person (their account, sessions, credentials, the
    instance) uses this, and so refuses an API token."""
    _refuse_api_token()
    return user


async def current_superuser(
    request: Request,
    user: User = Depends(_superuser),
    db: AsyncSession = Depends(get_async_session),
) -> User:
    _refuse_api_token()
    set_actor(user.id)
    await _enforce_mfa(request, user, db)
    return user
