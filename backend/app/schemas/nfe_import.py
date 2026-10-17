"""Schemas de importação de NF-e.

NF-e importada → Invoice com direction='payable', origin='imported',
external_source='nfe', external_id=chave_acesso (44 dígitos).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class NfeItemPreview(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal


class NfePreview(BaseModel):
    """Resultado do parse do XML — exibido para o usuário antes de confirmar."""
    chave_acesso: str
    numero: str
    serie: str
    issue_date: date
    emitente_cnpj: str
    emitente_nome: str
    valor_total: Decimal
    valor_produtos: Decimal
    valor_impostos: Decimal
    currency: str
    items: list[NfeItemPreview]
    notes: Optional[str] = None
    already_imported: bool = False   # True se a chave já existe neste workspace


class NfeConfirmRequest(BaseModel):
    """Corpo do POST de confirmação."""
    chave_acesso: str
    # Conta a pagar associada (obrigatório para criar o título)
    due_date: date
    # Payee a associar (opcional — o usuário pode criar na hora)
    payee_id: Optional[UUID] = None


class NfeImportResult(BaseModel):
    invoice_id: UUID
    chave_acesso: str
    emitente_nome: str
    valor_total: Decimal
    already_existed: bool
