from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AccrualScheduleCreate(BaseModel):
    type: Literal["accrual", "deferral"]
    description: str = Field(min_length=1, max_length=500)
    total_amount: Decimal = Field(gt=0)
    start_date: date
    end_date: date
    account_id: uuid.UUID
    category_id: Optional[uuid.UUID] = None
    cost_center_id: Optional[uuid.UUID] = None
    source_transaction_id: Optional[uuid.UUID] = None
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)


class AccrualEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    period_date: date
    amount: Decimal
    transaction_id: Optional[uuid.UUID] = None
    status: str
    posted_at: Optional[datetime] = None


class AccrualScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    description: str
    type: str
    total_amount: Decimal
    start_date: date
    end_date: date
    period_count: int
    amount_per_period: Decimal
    currency: str
    category_id: Optional[uuid.UUID] = None
    cost_center_id: Optional[uuid.UUID] = None
    account_id: Optional[uuid.UUID] = None
    source_transaction_id: Optional[uuid.UUID] = None
    is_active: bool
    created_at: datetime
    posted_count: int = 0
    pending_count: int = 0
    skipped_count: int = 0


class AccrualScheduleDetail(AccrualScheduleRead):
    entries: list[AccrualEntryRead] = []


class AccrualPostRequest(BaseModel):
    # Padrão: hoje. Lançamentos de meses futuros só saem se a data for informada.
    up_to_date: Optional[date] = None


class AccrualPostResult(BaseModel):
    posted: int
    skipped: int
