"""Schemas da API de conectores ERP (F3). Credenciais entram, nunca saem."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ErpProviderRead(BaseModel):
    key: str
    available: bool  # False = registrado mas ainda sem implementação (ex.: Conta Azul)


class ErpConnectionCreate(BaseModel):
    provider: str
    credentials: dict[str, Any]
    sync_config: dict[str, Any] = Field(default_factory=dict)


class ErpConnectionUpdate(BaseModel):
    credentials: Optional[dict[str, Any]] = None
    sync_config: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class ErpConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    provider: str
    is_active: bool
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    sync_config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ErpTestResult(BaseModel):
    ok: bool
    message: Optional[str] = None


class ErpSyncRequest(BaseModel):
    entity_type: str  # category | payee | transaction | invoice
    direction: Optional[str] = None  # pull | push — opcional; se vier, tem de bater com o tipo
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class ErpSyncQueued(BaseModel):
    queued: bool = True
    entity_type: str
    direction: str


class ErpSyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    connection_id: UUID
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    entity_type: Optional[str] = None
    direction: Optional[str] = None
    created_count: int
    updated_count: int
    error_count: int
    errors: list[Any] = Field(default_factory=list)


class ErpMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type: str
    local_id: UUID
    external_id: str
