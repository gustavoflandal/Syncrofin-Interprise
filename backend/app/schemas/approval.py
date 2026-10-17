from __future__ import annotations
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ApprovalRuleCreate(BaseModel):
    category_group_id: Optional[uuid.UUID] = None
    amount_threshold: Decimal = Field(..., gt=0)
    currency: str = Field(default="BRL", min_length=3, max_length=3)


class ApprovalRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    workspace_id: uuid.UUID
    category_group_id: Optional[uuid.UUID]
    amount_threshold: Decimal
    currency: str
    created_by_user_id: Optional[uuid.UUID]


class ApprovalEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    transaction_id: uuid.UUID
    actor_user_id: Optional[uuid.UUID]
    action: str
    note: Optional[str]
    occurred_at: datetime


class ApprovalActionRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=1000)


class ThresholdResponse(BaseModel):
    threshold: Optional[Decimal]
    currency: Optional[str]
    needs_approval: bool
