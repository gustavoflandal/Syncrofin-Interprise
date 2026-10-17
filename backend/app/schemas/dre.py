from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class DreLine(BaseModel):
    label: str
    amount: Decimal
    subcategories: list[DreLine] = []
    # Populated when the caller requested budget overlay
    budgeted: Optional[Decimal] = None


class DreGroupLine(BaseModel):
    group_name: str
    lines: list[DreLine]
    subtotal: Decimal
    budgeted: Optional[Decimal] = None


class DreSection(BaseModel):
    key: str    # "receita" | "despesa" | "custo" | "neutro"
    label: str
    groups: list[DreGroupLine]
    subtotal: Decimal
    budgeted: Optional[Decimal] = None


class DreReport(BaseModel):
    year: int
    month: int
    currency: str
    sections: list[DreSection]
    # Campos de compatibilidade retroativa — calculados a partir de sections
    gross_revenue: Decimal
    deductions: Decimal
    net_revenue: Decimal
    operating_expenses: Decimal
    result: Decimal
    cost_center_id: Optional[uuid.UUID] = None
    prev_month: Optional[DreReport] = None
    # Set when accounting_mode != default
    accounting_mode: str = "competence"
    # Set when show_budget=True; maps category label → budgeted amount
    budget_result: Optional[Decimal] = None

    model_config = {"from_attributes": True}


class DreQuarterlyReport(BaseModel):
    year: int
    quarter: int    # 1–4
    currency: str
    sections: list[DreSection]
    gross_revenue: Decimal
    operating_expenses: Decimal
    result: Decimal
    cost_center_id: Optional[uuid.UUID] = None
    months: list[DreReport]     # os 3 meses individuais


class DreAnnualReport(BaseModel):
    year: int
    currency: str
    sections: list[DreSection]
    gross_revenue: Decimal
    operating_expenses: Decimal
    result: Decimal
    cost_center_id: Optional[uuid.UUID] = None
    monthly: list[DreReport]    # 12 meses para tabela de sazonalidade


class DfcPeriod(BaseModel):
    date: str   # ISO date (primeiro dia da semana)
    inflows: Decimal
    outflows: Decimal
    balance: Decimal


class DfcReport(BaseModel):
    year: int
    month: int
    currency: str
    opening_balance: Decimal
    closing_balance: Decimal
    periods: list[DfcPeriod]
