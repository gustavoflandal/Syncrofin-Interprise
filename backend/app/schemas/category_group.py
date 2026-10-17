import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator

from app.schemas.category import CategoryRead

VALID_NATUREZAS = {"receita", "despesa", "custo", "neutro"}


class CategoryGroupBase(BaseModel):
    name: str
    icon: str = "folder"
    color: str = "#6B7280"
    position: int = 0
    code: Optional[str] = None
    natureza: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None

    @model_validator(mode="after")
    def validate_natureza(self) -> "CategoryGroupBase":
        if self.natureza is not None and self.natureza not in VALID_NATUREZAS:
            raise ValueError(f"natureza deve ser um de: {VALID_NATUREZAS}")
        return self


class CategoryGroupCreate(CategoryGroupBase):
    pass


class CategoryGroupUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    position: Optional[int] = None
    is_hidden: Optional[bool] = None
    code: Optional[str] = None
    natureza: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None

    @model_validator(mode="after")
    def validate_natureza(self) -> "CategoryGroupUpdate":
        if self.natureza is not None and self.natureza not in VALID_NATUREZAS:
            raise ValueError(f"natureza deve ser um de: {VALID_NATUREZAS}")
        return self


class CategoryGroupRead(CategoryGroupBase):
    id: uuid.UUID
    user_id: uuid.UUID
    is_system: bool
    is_hidden: bool = False
    depth: int = 0
    effective_natureza: Optional[str] = None
    categories: list[CategoryRead] = []
    children: list["CategoryGroupRead"] = []

    model_config = ConfigDict(from_attributes=True)

CategoryGroupRead.model_rebuild()
