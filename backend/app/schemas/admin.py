import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AdminUserRead(BaseModel):
    id: uuid.UUID
    email: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    is_2fa_enabled: bool = False
    # Set while the account is paused after too many wrong passwords; a time in the past means it is over.
    locked_until: Optional[datetime] = None
    preferences: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class AdminUserCreate(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)
    is_superuser: bool = False
    preferences: Optional[dict] = None


class AdminUserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, max_length=128)
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    preferences: Optional[dict] = None


class AdminUserList(BaseModel):
    items: list[AdminUserRead]
    total: int


class AppSettingRead(BaseModel):
    key: str
    value: str

    model_config = ConfigDict(from_attributes=True)


class AppSettingUpdate(BaseModel):
    value: str
