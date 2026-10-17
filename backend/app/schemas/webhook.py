"""Schemas para webhooks de saída por workspace (F2)."""
from datetime import datetime
from typing import Optional
import uuid

from pydantic import AnyHttpUrl, BaseModel, field_validator

from app.models.workspace_webhook import EVENT_TYPES


class WebhookCreate(BaseModel):
    url: AnyHttpUrl
    secret: Optional[str] = None
    # None/empty = todos os eventos; lista não vazia = filtro explícito.
    event_types: Optional[list[str]] = None

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None or len(v) == 0:
            return None
        unknown = set(v) - EVENT_TYPES
        if unknown:
            raise ValueError(f"Tipos de evento desconhecidos: {sorted(unknown)}")
        return v


class WebhookUpdate(BaseModel):
    url: Optional[AnyHttpUrl] = None
    secret: Optional[str] = None
    event_types: Optional[list[str]] = None
    active: Optional[bool] = None

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None or len(v) == 0:
            return None
        unknown = set(v) - EVENT_TYPES
        if unknown:
            raise ValueError(f"Tipos de evento desconhecidos: {sorted(unknown)}")
        return v


class WebhookRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    url: str
    # O segredo nunca é retornado; apenas um booleano indica se está configurado.
    has_secret: bool
    event_types: Optional[list[str]]   # None = todos os eventos
    active: bool
    created_at: datetime
    last_fired_at: Optional[datetime]
    last_status_code: Optional[int]

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, obj: object) -> "WebhookRead":  # type: ignore[override]
        from app.models.workspace_webhook import WorkspaceWebhook
        assert isinstance(obj, WorkspaceWebhook)
        return cls(
            id=obj.id,
            workspace_id=obj.workspace_id,
            url=obj.url,
            has_secret=bool(obj.secret),
            event_types=obj.event_types,
            active=obj.active,
            created_at=obj.created_at,
            last_fired_at=obj.last_fired_at,
            last_status_code=obj.last_status_code,
        )
