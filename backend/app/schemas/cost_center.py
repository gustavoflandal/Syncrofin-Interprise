import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CostCenterCreate(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None


class CostCenterUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CostCenterRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    code: Optional[str] = None
    description: Optional[str] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
