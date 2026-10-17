"""Schemas de configuração e emissão fiscal (B1)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FiscalProviderConfigRead(BaseModel):
    workspace_id: UUID
    provider: str
    environment: str
    cnpj_emitente: Optional[str] = None
    serie_padrao: str
    # api_key não é devolvida — apenas indica se há uma configurada
    has_api_key: bool
    updated_at: datetime


class FiscalProviderConfigSave(BaseModel):
    provider: str
    api_key: str           # plaintext — cifrado no serviço
    environment: str       # 'homologation' | 'production'
    cnpj_emitente: Optional[str] = None
    serie_padrao: str = "1"


class FiscalEmissionRead(BaseModel):
    id: UUID
    workspace_id: UUID
    invoice_id: UUID
    provider: str
    environment: str
    status: str
    provider_ref: Optional[str] = None
    chave_acesso: Optional[str] = None
    nfe_number: Optional[str] = None
    nfe_serie: Optional[str] = None
    xml_url: Optional[str] = None
    pdf_url: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class EmitNfeRequest(BaseModel):
    invoice_id: UUID


class CancelEmissionRequest(BaseModel):
    justificativa: str = "Cancelamento solicitado pelo emitente"
