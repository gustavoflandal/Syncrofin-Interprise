from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi_users.exceptions import InvalidPasswordException

from app.core import password_policy
from app.core.auth import get_user_manager, UserManager
from app.services import session_service
from app.core.auth_policy import require_local_auth_enabled
from app.core.config import get_settings
from app.core.defaults import default_preferences
from app.core.database import get_async_session
from app.models.account import Account
from app.models.user import User

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupStatus(BaseModel):
    has_users: bool


class CreateAdminRequest(BaseModel):
    email: EmailStr
    password: str
    currency: str = Field(default_factory=lambda: get_settings().default_currency)
    name: str = ""
    language: str = Field(default_factory=lambda: get_settings().default_language)


@router.get("/status", response_model=SetupStatus)
async def get_setup_status(session: AsyncSession = Depends(get_async_session)):
    result = await session.execute(select(func.count(User.id)))
    count = result.scalar() or 0
    return SetupStatus(has_users=count > 0)


@router.post("/create-admin", dependencies=[Depends(require_local_auth_enabled)])
async def create_admin(
    body: CreateAdminRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_async_session),
    user_manager: UserManager = Depends(get_user_manager),
):
    # Check if users already exist
    result = await session.execute(select(func.count(User.id)))
    count = result.scalar() or 0
    if count > 0:
        raise HTTPException(status_code=403, detail="Setup already completed")

    from fastapi_users import schemas

    user_create = schemas.BaseUserCreate(
        email=body.email,
        password=body.password,
        is_superuser=True,
    )
    try:
        user = await user_manager.create(user_create)
    except InvalidPasswordException as e:
        raise HTTPException(status_code=400, detail=password_policy.http_detail(str(e.reason)))

    # Build preferences dict
    prefs = {
        **default_preferences(),
        "currency_display": body.currency,
        "language": body.language,
        "onboarding_completed": False,
    }
    if body.name:
        prefs["display_name"] = body.name

    # Use direct SQL update to avoid session expiry issues after user_manager.create() commits
    db_session = user_manager.user_db.session
    await db_session.execute(
        sql_update(User).where(User.id == user.id).values(preferences=prefs)
    )

    # Personal workspace gets auto-created here too (setup endpoint runs
    # programmatically, so the registration hook's `request is None` early
    # exit fires; we have to set up the workspace ourselves).
    from app.services.workspace_service import create_personal_workspace_for_user

    await db_session.refresh(user)
    workspace = await create_personal_workspace_for_user(db_session, user)

    # Create default wallet with the chosen currency
    wallet_name = "Carteira" if body.language.startswith("pt") else "Wallet"
    wallet = Account(
        user_id=user.id,
        workspace_id=workspace.id,
        name=wallet_name,
        type="checking",
        balance=Decimal("0.00"),
        currency=body.currency,
    )
    db_session.add(wallet)
    await db_session.commit()

    # Create default categories and rules for the new user
    from app.services.category_service import create_default_categories
    from app.services.rule_service import create_default_rules

    await create_default_categories(db_session, user.id, body.language, workspace_id=workspace.id)
    await create_default_rules(db_session, user.id, body.language, workspace_id=workspace.id)

    # Refresh user to get updated preferences for token generation
    await db_session.refresh(user)

    return await session_service.sign_in(db_session, user, request, response, "setup")
