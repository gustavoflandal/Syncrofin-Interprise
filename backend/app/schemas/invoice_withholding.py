import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

WithholdingTaxType = Literal["irrf", "iss", "pis", "cofins", "csll", "inss", "other"]


class WithholdingCreate(BaseModel):
    tax_type: WithholdingTaxType
    rate: Optional[Decimal] = Field(default=None, ge=0, le=100)
    base_amount: Decimal = Field(..., ge=0)
    withheld_amount: Decimal = Field(..., gt=0)


class WithholdingUpdate(BaseModel):
    tax_type: Optional[WithholdingTaxType] = None
    rate: Optional[Decimal] = Field(default=None, ge=0, le=100)
    base_amount: Optional[Decimal] = Field(default=None, ge=0)
    withheld_amount: Optional[Decimal] = Field(default=None, gt=0)


class WithholdingRead(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    tax_type: str
    rate: Optional[Decimal] = None
    base_amount: Decimal
    withheld_amount: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
