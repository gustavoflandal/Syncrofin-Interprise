"""Schemas for the consolidated AP/AR overview, title list and cash-flow forecast.

Produced by `ar_ap_service`. Keeps both sides of the ledger —
what clients owe us (receivable) and what we owe suppliers (payable) — in one
response so a dashboard does not need two separate calls.
"""
from datetime import date as _Date
from decimal import Decimal
from typing import Optional
import uuid

from pydantic import BaseModel


class UpcomingInvoice(BaseModel):
    id: uuid.UUID
    number: Optional[int]
    series: Optional[str]
    due_date: str          # ISO date string
    total: Decimal
    balance: Decimal
    payee_name: Optional[str]

    model_config = {"from_attributes": True}


class AgingSide(BaseModel):
    outstanding: Decimal        # total em aberto (não pago)
    overdue_amount: Decimal     # total vencido
    overdue_count: int
    current: Decimal            # a vencer (bucket current)
    d1_30: Decimal
    d31_60: Decimal
    d61_90: Decimal
    d90_plus: Decimal
    collected_this_month: Decimal
    upcoming: list[UpcomingInvoice]


class ArApOverview(BaseModel):
    receivable: AgingSide
    payable: AgingSide
    net_position: Decimal       # receivable.outstanding - payable.outstanding


class TitleRead(BaseModel):
    """Lightweight invoice row for the AP/AR title list."""

    id: uuid.UUID
    direction: str
    state: str
    number: Optional[int]
    series: Optional[str]
    external_number: Optional[str] = None
    issue_date: _Date
    due_date: _Date
    currency: str
    total: Decimal
    balance: Decimal
    days_overdue: int
    payee_id: Optional[uuid.UUID]
    payee_name: Optional[str]

    model_config = {"from_attributes": True}


class TitlesPage(BaseModel):
    items: list[TitleRead]
    total: int
    page: int
    page_size: int


class ForecastBucket(BaseModel):
    """One time bucket in the cash-flow forecast."""

    label: str           # e.g. "2026-10", "2026-W41"
    period_start: _Date
    period_end: _Date
    receivable: Decimal
    payable: Decimal
    taxes: Decimal = Decimal("0")  # obrigações fiscais (recorrências com tax_obligation_type)
    net: Decimal


class CashFlowForecast(BaseModel):
    currency: str
    period: str          # "week" | "month"
    buckets: list[ForecastBucket]


class NfeImportRow(BaseModel):
    """Resultado da importação de um único arquivo NF-e."""

    filename: str
    status: str          # "imported" | "duplicate" | "error"
    invoice_id: Optional[uuid.UUID] = None
    chave: Optional[str] = None
    supplier_name: Optional[str] = None
    total: Optional[Decimal] = None
    error: Optional[str] = None


class NfeImportResult(BaseModel):
    rows: list[NfeImportRow]
    imported: int
    duplicates: int
    errors: int


class TaxObligationSummary(BaseModel):
    """Obrigações fiscais do mês corrente, somadas por tipo (das, darf, iss...)."""

    month: _Date
    total: Decimal
    by_type: dict[str, Decimal]
