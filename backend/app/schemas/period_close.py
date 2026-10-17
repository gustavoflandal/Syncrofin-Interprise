from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field


class PeriodCloseCreate(BaseModel):
    year: int = Field(..., ge=2000, le=2100)
    month: int = Field(..., ge=1, le=12)
    reason: Optional[str] = Field(default=None, max_length=500)


class PeriodReopenRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class PeriodCloseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    year: int
    month: int
    closed_by_user_id: Optional[uuid.UUID]
    closed_at: datetime
    reason: Optional[str]
    reopened_by_user_id: Optional[uuid.UUID]
    reopened_at: Optional[datetime]
    reopen_reason: Optional[str]

    @computed_field  # type: ignore[misc]
    @property
    def is_open(self) -> bool:
        return self.reopened_at is not None
