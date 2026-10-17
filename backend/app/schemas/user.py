import uuid
from typing import Optional

from fastapi_users import schemas
from pydantic import BaseModel, Field

from app.core.config import get_settings


class UserPreferences(BaseModel):
    language: str = Field(default_factory=lambda: get_settings().default_language)
    date_format: str = Field(default_factory=lambda: get_settings().default_date_format)
    timezone: str = Field(default_factory=lambda: get_settings().default_timezone)
    currency_display: str = Field(default_factory=lambda: get_settings().default_currency)
    onboarding_completed: bool = False


class UserRead(schemas.BaseUser[uuid.UUID]):
    preferences: Optional[dict] = None
    is_2fa_enabled: bool = False


class UserCreate(schemas.BaseUserCreate):
    preferences: Optional[dict] = None


class UserUpdate(schemas.BaseUserUpdate):
    preferences: Optional[dict] = None
