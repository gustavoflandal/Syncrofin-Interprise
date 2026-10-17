from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RetentionPolicyRead(BaseModel):
    id: UUID
    workspace_id: UUID
    transaction_retention_days: int
    attachment_retention_days: int
    audit_retention_days: int
    anonymize_on_expiry: bool
    last_purge_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RetentionPolicyUpdate(BaseModel):
    transaction_retention_days: Optional[int] = Field(None, ge=365)
    attachment_retention_days: Optional[int] = Field(None, ge=365)
    audit_retention_days: Optional[int] = Field(None, ge=365)
    anonymize_on_expiry: Optional[bool] = None
