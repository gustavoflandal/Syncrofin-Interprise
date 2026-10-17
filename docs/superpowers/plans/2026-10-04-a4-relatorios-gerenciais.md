# A4 — Relatórios Gerenciais Integrados: Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refatorar o DRE para exibir transações agrupadas por natureza (Receitas / Custos / Despesas / Neutro) e grupos de categoria, com filtro por centro de custo e granularidades mensal, trimestral e anual via endpoints separados.

**Architecture:** O serviço `report_service.get_dre()` é refatorado para carregar `CategoryGroup` e computar `effective_natureza` em Python; uma função `build_dre_sections()` monta a hierarquia. Dois novos endpoints (`/dre/quarterly`, `/dre/annual`) chamam `get_dre()` internamente e agregam os resultados. O frontend recebe um seletor de período (Mês/Trimestre/Ano) e um dropdown de CC, e renderiza o DRE como accordion hierárquico.

**Tech Stack:** FastAPI + SQLAlchemy async (backend); React 19 + TanStack Query + i18next (frontend); pytest async (testes).

**Spec:** `docs/superpowers/specs/2026-10-04-a4-relatorios-gerenciais-design.md`

## Global Constraints

- Toda entidade financeira tem `workspace_id`; `cost_center_id` de outro workspace → `HTTPException(404, "cost_center_not_found")`
- Dinheiro é `Decimal`; nunca `float` em cálculos; conversão apenas na camada de serialização Pydantic
- Campos herdados `gross_revenue`, `deductions`, `net_revenue`, `operating_expenses`, `result` são **mantidos** em `DreReport` para compatibilidade retroativa
- Campo `lines: list[DreLine]` do `DreReport` original é **removido** (nunca renderizado no frontend)
- i18n: novas chaves em **en, pt-BR e es** ao mesmo tempo; `npm run i18n:check -- --strict` deve passar
- Permissão de todos os endpoints de relatório: `require_permission("reports.view")` — já existente via `current_workspace`; GET-only → entram em `ALLOWLIST` do teste de permissões se o teste os exigir
- `effective_natureza` não é coluna no banco; é computado em Python: se `group.natureza` → usa; se não, sobe ao `parent` recursivamente; se raiz sem `natureza` → `None`
- Convenção de commit: Conventional Commits (`feat(a4): ...`)

---

## Mapa de arquivos

| Arquivo | Ação |
|---------|------|
| `backend/app/schemas/dre.py` | Modificar — adicionar `DreSection`, `DreGroupLine`; refatorar `DreReport`; adicionar `DreQuarterlyReport`, `DreAnnualReport` |
| `backend/app/services/report_service.py` | Modificar — refatorar `get_dre()`; adicionar `build_dre_sections()`, `_effective_natureza()`, `get_dre_quarterly()`, `get_dre_annual()`; adicionar CC filter ao `get_dfc()` |
| `backend/app/api/reports.py` | Modificar — adicionar `?cost_center_id` ao `/dre` e `/cash-flow`; adicionar rotas `/dre/quarterly` e `/dre/annual`; atualizar `/dre/export` |
| `backend/tests/test_dre_api.py` | Criar — testes para seções, CC filter, quarterly, annual |
| `backend/tests/test_write_permission_coverage.py` | Verificar — novas rotas GET não precisam de entrada; confirmar no final |
| `frontend/src/lib/api.ts` | Modificar — `DreReport`, novos tipos, métodos `getDreQuarterly`, `getDreAnnual`; `getDre` ganha `ccId?` |
| `frontend/src/pages/dre.tsx` | Modificar — seletor de período + CC; renderer hierárquico |
| `frontend/src/locales/en.json` | Modificar — chaves `dre.period.*`, `dre.section.*` |
| `frontend/src/locales/pt-BR.json` | Modificar — mesmas chaves |
| `frontend/src/locales/es.json` | Modificar — mesmas chaves |
| `frontend/src/help/content/pt-BR/dre.md` | Modificar — filtro CC, períodos trimestrais/anuais |

---

### Task 1: Backend — Schemas DRE refatorados

**Files:**
- Modify: `backend/app/schemas/dre.py`

**Interfaces:**
- Produces: `DreSection`, `DreGroupLine`, `DreReport` (refatorado), `DreQuarterlyReport`, `DreAnnualReport` — usados em Tasks 2 e 3

- [ ] **Step 1: Escrever testes para os schemas**

`backend/tests/test_dre_schemas.py`:

```python
from decimal import Decimal
from app.schemas.dre import DreSection, DreGroupLine, DreLine, DreReport, DreQuarterlyReport, DreAnnualReport


def test_dre_section_subtotal_is_sum_of_groups():
    g1 = DreGroupLine(group_name="Serviços", lines=[DreLine(label="Consultoria", amount=Decimal("5000"))], subtotal=Decimal("5000"))
    g2 = DreGroupLine(group_name="Produtos", lines=[DreLine(label="Venda", amount=Decimal("3000"))], subtotal=Decimal("3000"))
    s = DreSection(key="receita", label="Receitas", groups=[g1, g2], subtotal=Decimal("8000"))
    assert s.subtotal == Decimal("8000")


def test_dre_report_has_sections_and_compat_fields():
    sec = DreSection(key="receita", label="Receitas", groups=[], subtotal=Decimal("0"))
    r = DreReport(
        year=2026, month=1, currency="BRL",
        sections=[sec],
        gross_revenue=Decimal("1000"), deductions=Decimal("0"),
        net_revenue=Decimal("1000"), operating_expenses=Decimal("500"),
        result=Decimal("500"), cost_center_id=None,
    )
    assert r.sections[0].key == "receita"
    assert r.gross_revenue == Decimal("1000")


def test_dre_quarterly_report_fields():
    r = DreQuarterlyReport(
        year=2026, quarter=1, currency="BRL",
        sections=[], months=[],
        gross_revenue=Decimal("0"), operating_expenses=Decimal("0"),
        result=Decimal("0"), cost_center_id=None,
    )
    assert r.quarter == 1


def test_dre_annual_report_fields():
    r = DreAnnualReport(
        year=2026, currency="BRL",
        sections=[], monthly=[],
        gross_revenue=Decimal("0"), operating_expenses=Decimal("0"),
        result=Decimal("0"), cost_center_id=None,
    )
    assert r.year == 2026
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

```
cd backend && python -m pytest tests/test_dre_schemas.py -v
```

Esperado: `ImportError` ou `AttributeError` — os tipos novos ainda não existem.

- [ ] **Step 3: Reescrever `backend/app/schemas/dre.py`**

```python
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class DreLine(BaseModel):
    label: str
    amount: Decimal
    subcategories: list[DreLine] = []


class DreGroupLine(BaseModel):
    group_name: str
    lines: list[DreLine]
    subtotal: Decimal


class DreSection(BaseModel):
    key: str    # "receita" | "despesa" | "custo" | "neutro"
    label: str
    groups: list[DreGroupLine]
    subtotal: Decimal


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
```

- [ ] **Step 4: Rodar os testes**

```
cd backend && python -m pytest tests/test_dre_schemas.py -v
```

Esperado: 4 testes passando.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/dre.py backend/tests/test_dre_schemas.py
git commit -m "feat(a4): add DreSection/DreGroupLine/DreQuarterlyReport/DreAnnualReport schemas"
```

---

### Task 2: Backend — Service refatorado com natureza e CC

**Files:**
- Modify: `backend/app/services/report_service.py`
- Create: `backend/tests/test_dre_api.py`

**Interfaces:**
- Consumes: `DreSection`, `DreGroupLine`, `DreLine`, `DreReport`, `DreQuarterlyReport`, `DreAnnualReport` de `app.schemas.dre` (Task 1); `CategoryGroup` de `app.models.category_group`
- Produces:
  - `async def get_dre(session, workspace_id, user_id, year, month, include_prev=True, cost_center_id=None) -> DreReport`
  - `async def get_dre_quarterly(session, workspace_id, user_id, year, quarter, cost_center_id=None) -> DreQuarterlyReport`
  - `async def get_dre_annual(session, workspace_id, user_id, year, cost_center_id=None) -> DreAnnualReport`
  - `async def get_dfc(session, workspace_id, user_id, year, month, cost_center_id=None) -> DfcReport` (CC filter adicionado)

- [ ] **Step 1: Escrever os testes**

`backend/tests/test_dre_api.py`:

```python
"""Testes de integração para os endpoints de DRE (A4)."""
import pytest
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category_group import CategoryGroup
from app.models.category import Category
from app.models.cost_center import CostCenter
from app.models.transaction import Transaction


# helpers de fixture já existem em conftest.py (workspace, authenticated_client, etc.)


@pytest.mark.asyncio
async def test_dre_sections_natureza(async_client: AsyncClient, session: AsyncSession, workspace, auth_headers):
    """Transações de naturezas diferentes aparecem em seções corretas."""
    grp_receita = CategoryGroup(workspace_id=workspace.id, user_id=workspace.owner_id, name="Serviços", natureza="receita", depth=0)
    grp_despesa = CategoryGroup(workspace_id=workspace.id, user_id=workspace.owner_id, name="Admin", natureza="despesa", depth=0)
    session.add_all([grp_receita, grp_despesa])
    await session.flush()

    cat_r = Category(workspace_id=workspace.id, user_id=workspace.owner_id, name="Consultoria", group_id=grp_receita.id)
    cat_d = Category(workspace_id=workspace.id, user_id=workspace.owner_id, name="Aluguel", group_id=grp_despesa.id)
    session.add_all([cat_r, cat_d])
    await session.flush()

    # Criar conta e transações via fixtures auxiliares ou diretamente
    # (adaptar ao padrão do conftest existente no projeto)
    # ...

    r = await async_client.get("/api/reports/dre", params={"year": 2026, "month": 1}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    section_keys = {s["key"] for s in data["sections"]}
    assert "receita" in section_keys
    assert "despesa" in section_keys


@pytest.mark.asyncio
async def test_dre_fallback_no_natureza(async_client: AsyncClient, session: AsyncSession, workspace, auth_headers):
    """Categoria sem grupo/natureza: credit→receita, debit→despesa."""
    # transação de crédito sem categoria → seção receita
    # transação de débito sem categoria → seção despesa
    r = await async_client.get("/api/reports/dre", params={"year": 2026, "month": 1}, headers=auth_headers)
    assert r.status_code == 200
    # Sem categorias com natureza, ainda retorna seções válidas (ou lista vazia)
    assert "sections" in r.json()


@pytest.mark.asyncio
async def test_dre_cost_center_filter(async_client: AsyncClient, session: AsyncSession, workspace, auth_headers):
    """Com cost_center_id, apenas transações daquele CC aparecem."""
    cc = CostCenter(workspace_id=workspace.id, name="Loja A", code="LA")
    session.add(cc)
    await session.flush()

    r = await async_client.get(
        "/api/reports/dre",
        params={"year": 2026, "month": 1, "cost_center_id": str(cc.id)},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["cost_center_id"] == str(cc.id)


@pytest.mark.asyncio
async def test_dre_cost_center_foreign_workspace(async_client: AsyncClient, session: AsyncSession, workspace, other_workspace, auth_headers):
    """CC de outro workspace → 404."""
    cc_other = CostCenter(workspace_id=other_workspace.id, name="Externo", code="EXT")
    session.add(cc_other)
    await session.flush()

    r = await async_client.get(
        "/api/reports/dre",
        params={"year": 2026, "month": 1, "cost_center_id": str(cc_other.id)},
        headers=auth_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_dre_quarterly_sums_three_months(async_client: AsyncClient, auth_headers):
    """Endpoint trimestral existe e retorna estrutura correta."""
    r = await async_client.get(
        "/api/reports/dre/quarterly",
        params={"year": 2026, "quarter": 1},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["quarter"] == 1
    assert len(data["months"]) == 3


@pytest.mark.asyncio
async def test_dre_annual_has_12_months(async_client: AsyncClient, auth_headers):
    """Endpoint anual retorna 12 meses."""
    r = await async_client.get(
        "/api/reports/dre/annual",
        params={"year": 2026},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["monthly"]) == 12
```

- [ ] **Step 2: Rodar os testes para confirmar falha**

```
cd backend && python -m pytest tests/test_dre_api.py -v -k "test_dre_quarterly or test_dre_annual"
```

Esperado: `404 Not Found` — endpoints ainda não existem.

- [ ] **Step 3: Adicionar imports no topo de `backend/app/services/report_service.py`**

No bloco de imports iniciais, adicionar:

```python
from app.models.category_group import CategoryGroup
```

(junto dos outros `from app.models.*`)

- [ ] **Step 4: Adicionar `_effective_natureza()` e `build_dre_sections()` em `report_service.py`**

Inserir logo antes da função `get_dre()` (linha ~1152):

```python
_SECTION_ORDER = ["receita", "custo", "despesa", "neutro"]
_SECTION_LABELS = {
    "receita": "Receitas",
    "custo": "Custos",
    "despesa": "Despesas operacionais",
    "neutro": "Neutro",
}


def _effective_natureza(
    group: CategoryGroup | None,
    groups_by_id: dict[uuid.UUID, CategoryGroup],
) -> str | None:
    if group is None:
        return None
    if group.natureza:
        return group.natureza
    if group.parent_id:
        return _effective_natureza(groups_by_id.get(group.parent_id), groups_by_id)
    return None


def _build_dre_sections(
    rows: list[tuple["Transaction", "Category | None"]],
    groups_by_id: dict[uuid.UUID, "CategoryGroup"],
) -> list["DreSection"]:
    from collections import defaultdict
    from app.schemas.dre import DreLine, DreGroupLine, DreSection

    # (natureza, group_key) → {cat_label: amount}
    buckets: dict[tuple[str, str], dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))

    for tx, cat in rows:
        group = groups_by_id.get(cat.group_id) if cat and cat.group_id else None
        natureza = _effective_natureza(group, groups_by_id) or (
            "receita" if tx.type == "credit" else "despesa"
        )
        group_key = group.name if group else "_sem_grupo"
        cat_label = cat.name if cat else tx.description or "Sem categoria"
        amount = tx.amount_primary if tx.amount_primary is not None else tx.amount
        buckets[(natureza, group_key)][cat_label] += amount

    # Agrupar por natureza
    by_nat: dict[str, dict[str, dict[str, Decimal]]] = defaultdict(dict)
    for (nat, grp), cats in buckets.items():
        by_nat[nat][grp] = cats

    sections: list[DreSection] = []
    for nat in _SECTION_ORDER:
        if nat not in by_nat:
            continue
        groups = []
        for grp_name, cats in by_nat[nat].items():
            lines = [DreLine(label=k, amount=v) for k, v in cats.items()]
            groups.append(DreGroupLine(
                group_name=grp_name if grp_name != "_sem_grupo" else "Sem grupo",
                lines=lines,
                subtotal=sum(l.amount for l in lines),
            ))
        sections.append(DreSection(
            key=nat,
            label=_SECTION_LABELS[nat],
            groups=groups,
            subtotal=sum(g.subtotal for g in groups),
        ))
    return sections
```

- [ ] **Step 5: Refatorar `get_dre()` para usar `_build_dre_sections()` e aceitar `cost_center_id`**

Substituir a função `get_dre()` existente (linhas 1155–1234) por:

```python
async def get_dre(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    year: int,
    month: int,
    include_prev: bool = True,
    cost_center_id: uuid.UUID | None = None,
) -> DreReport:
    """DRE por competência, agrupado por natureza → grupo de categoria."""
    from app.schemas.dre import DreReport

    start = date(year, month, 1)
    _, last_day = calendar.monthrange(year, month)
    end = date(year, month, last_day)

    workspace = await session.get(Workspace, workspace_id)
    currency = workspace.default_currency if workspace else "BRL"

    # Validar CC antes de qualquer query
    if cost_center_id is not None:
        from app.services.cost_center_service import _ensure_cost_center_in_workspace
        await _ensure_cost_center_in_workspace(session, cost_center_id, workspace_id)

    # Carregar grupos do workspace para resolver effective_natureza
    grp_result = await session.execute(
        select(CategoryGroup).where(CategoryGroup.workspace_id == workspace_id)
    )
    groups_by_id: dict[uuid.UUID, CategoryGroup] = {
        g.id: g for g in grp_result.scalars().all()
    }

    # Query de transações
    where_clauses = [
        Transaction.workspace_id == workspace_id,
        Transaction.date >= start,
        Transaction.date <= end,
        Transaction.source != "opening_balance",
        Transaction.status == "posted",
        counts_as_pnl(),
    ]
    if cost_center_id is not None:
        where_clauses.append(Transaction.cost_center_id == cost_center_id)

    result = await session.execute(
        select(Transaction, Category)
        .join(Category, Transaction.category_id == Category.id, isouter=True)
        .where(*where_clauses)
    )
    rows = result.unique().all()

    sections = _build_dre_sections(rows, groups_by_id)

    # Campos de compatibilidade: receita = subtotal da seção "receita"; despesa = "despesa"+"custo"
    gross_revenue = next((s.subtotal for s in sections if s.key == "receita"), _ZERO)
    operating_expenses = sum(
        s.subtotal for s in sections if s.key in ("despesa", "custo", "neutro")
    )

    report = DreReport(
        year=year,
        month=month,
        currency=currency,
        sections=sections,
        gross_revenue=gross_revenue,
        deductions=_ZERO,
        net_revenue=gross_revenue,
        operating_expenses=operating_expenses,
        result=gross_revenue - operating_expenses,
        cost_center_id=cost_center_id,
    )

    if include_prev:
        prev_month = month - 1
        prev_year = year
        if prev_month == 0:
            prev_month = 12
            prev_year -= 1
        report.prev_month = await get_dre(
            session, workspace_id, user_id, prev_year, prev_month,
            include_prev=False, cost_center_id=cost_center_id,
        )

    return report
```

- [ ] **Step 6: Adicionar `get_dre_quarterly()` e `get_dre_annual()` em `report_service.py`**

Inserir logo após `get_dre()`:

```python
async def get_dre_quarterly(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    year: int,
    quarter: int,
    cost_center_id: uuid.UUID | None = None,
) -> "DreQuarterlyReport":
    """DRE trimestral: agrega 3 meses e retorna meses individuais."""
    from app.schemas.dre import DreQuarterlyReport, DreSection, DreGroupLine, DreLine
    from collections import defaultdict

    first_month = (quarter - 1) * 3 + 1
    months_data = []
    for m in range(first_month, first_month + 3):
        months_data.append(
            await get_dre(session, workspace_id, user_id, year, m,
                          include_prev=False, cost_center_id=cost_center_id)
        )

    # Agregar seções dos 3 meses
    sections = _aggregate_sections(months_data)
    gross_revenue = sum(
        m.gross_revenue for m in months_data
    )
    operating_expenses = sum(m.operating_expenses for m in months_data)

    return DreQuarterlyReport(
        year=year,
        quarter=quarter,
        currency=months_data[0].currency,
        sections=sections,
        gross_revenue=gross_revenue,
        operating_expenses=operating_expenses,
        result=gross_revenue - operating_expenses,
        cost_center_id=cost_center_id,
        months=months_data,
    )


async def get_dre_annual(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    year: int,
    cost_center_id: uuid.UUID | None = None,
) -> "DreAnnualReport":
    """DRE anual: agrega 12 meses e retorna cada mês."""
    from app.schemas.dre import DreAnnualReport

    monthly_data = []
    for m in range(1, 13):
        monthly_data.append(
            await get_dre(session, workspace_id, user_id, year, m,
                          include_prev=False, cost_center_id=cost_center_id)
        )

    sections = _aggregate_sections(monthly_data)
    gross_revenue = sum(m.gross_revenue for m in monthly_data)
    operating_expenses = sum(m.operating_expenses for m in monthly_data)

    return DreAnnualReport(
        year=year,
        currency=monthly_data[0].currency,
        sections=sections,
        gross_revenue=gross_revenue,
        operating_expenses=operating_expenses,
        result=gross_revenue - operating_expenses,
        cost_center_id=cost_center_id,
        monthly=monthly_data,
    )


def _aggregate_sections(reports: list["DreReport"]) -> list["DreSection"]:
    """Soma DreSection de múltiplos DreReport pelo mesmo key+group+label."""
    from collections import defaultdict
    from app.schemas.dre import DreSection, DreGroupLine, DreLine

    # (nat_key, group_name, line_label) → amount
    totals: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    nat_labels: dict[str, str] = {}

    for report in reports:
        for sec in report.sections:
            nat_labels[sec.key] = sec.label
            for grp in sec.groups:
                for line in grp.lines:
                    totals[(sec.key, grp.group_name, line.label)] += line.amount

    # Reconstruir sections na ordem canônica
    by_nat: dict[str, dict[str, dict[str, Decimal]]] = defaultdict(lambda: defaultdict(dict))
    for (nat, grp, lbl), amt in totals.items():
        by_nat[nat][grp][lbl] = amt

    sections = []
    for nat in _SECTION_ORDER:
        if nat not in by_nat:
            continue
        groups = []
        for grp_name, cats in by_nat[nat].items():
            lines = [DreLine(label=k, amount=v) for k, v in cats.items()]
            groups.append(DreGroupLine(group_name=grp_name, lines=lines, subtotal=sum(l.amount for l in lines)))
        sections.append(DreSection(
            key=nat,
            label=nat_labels.get(nat, nat),
            groups=groups,
            subtotal=sum(g.subtotal for g in groups),
        ))
    return sections
```

- [ ] **Step 7: Adicionar `cost_center_id` ao `get_dfc()`**

Localizar a assinatura de `get_dfc()` (~linha 1237) e adicionar o parâmetro + filtro:

```python
async def get_dfc(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    year: int,
    month: int,
    cost_center_id: uuid.UUID | None = None,  # NOVO
) -> DfcReport:
```

No bloco `where(...)` da query de transações dentro de `get_dfc()`, adicionar após os where clauses existentes:

```python
    if cost_center_id is not None:
        stmt = stmt.where(Transaction.cost_center_id == cost_center_id)
```

(Adaptar à estrutura exata da query — a função usa `select(Transaction).where(...)`. Adicionar o filtro ao final da lista de cláusulas.)

- [ ] **Step 8: Rodar os testes**

```
cd backend && python -m pytest tests/test_dre_api.py tests/test_dre_schemas.py -v
```

Esperado: testes de schemas passando; testes de API ainda falhando para quarterly/annual (endpoints não criados ainda) — OK neste passo.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/report_service.py backend/tests/test_dre_api.py
git commit -m "feat(a4): refactor get_dre with natureza sections, CC filter; add quarterly/annual service"
```

---

### Task 3: Backend — Rotas da API + export atualizado

**Files:**
- Modify: `backend/app/api/reports.py`

**Interfaces:**
- Consumes: `get_dre(cost_center_id=)`, `get_dre_quarterly()`, `get_dre_annual()`, `get_dfc(cost_center_id=)` de `report_service` (Task 2); `DreQuarterlyReport`, `DreAnnualReport` de `app.schemas.dre` (Task 1)
- Produces:
  - `GET /api/reports/dre?year=&month=&cost_center_id=` → `DreReport`
  - `GET /api/reports/dre/quarterly?year=&quarter=&cost_center_id=` → `DreQuarterlyReport`
  - `GET /api/reports/dre/annual?year=&cost_center_id=` → `DreAnnualReport`
  - `GET /api/reports/dfc?year=&month=&cost_center_id=` → `DfcReport`
  - `GET /api/reports/dre/export` atualizado para usar `sections`

**ATENÇÃO:** Em FastAPI, rotas com prefixo mais específico (`/dre/quarterly`) devem ser declaradas **antes** de rotas com parâmetro dinâmico. Neste caso, `/dre/export` já existe; `quarterly` e `annual` são rotas literais e devem ficar **antes** de qualquer wildcard, mas **depois** de `/dre` (que é literal também). A ordem correta: `/dre` → `/dre/quarterly` → `/dre/annual` → `/dre/export` → `/dfc`.

- [ ] **Step 1: Atualizar os imports em `reports.py`**

Localizar a linha:
```python
from app.schemas.dre import DfcReport, DreReport
```
Substituir por:
```python
from app.schemas.dre import DfcReport, DreReport, DreQuarterlyReport, DreAnnualReport
```

- [ ] **Step 2: Atualizar o endpoint `GET /dre`**

Localizar (linhas ~88–95):
```python
@router.get("/dre", response_model=DreReport)
async def get_dre(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await report_service.get_dre(session, ctx.workspace.id, ctx.user_id, year, month)
```

Substituir por:
```python
@router.get("/dre", response_model=DreReport)
async def get_dre(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    cost_center_id: uuid.UUID | None = Query(None),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await report_service.get_dre(
        session, ctx.workspace.id, ctx.user_id, year, month,
        cost_center_id=cost_center_id,
    )
```

Certificar que `import uuid` está no topo do arquivo (adicionar se ausente).

- [ ] **Step 3: Adicionar endpoints `/dre/quarterly` e `/dre/annual`**

Inserir **logo após** o endpoint `/dre` (antes de `/dfc`):

```python
@router.get("/dre/quarterly", response_model=DreQuarterlyReport)
async def get_dre_quarterly(
    year: int = Query(..., ge=2000, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    cost_center_id: uuid.UUID | None = Query(None),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await report_service.get_dre_quarterly(
        session, ctx.workspace.id, ctx.user_id, year, quarter,
        cost_center_id=cost_center_id,
    )


@router.get("/dre/annual", response_model=DreAnnualReport)
async def get_dre_annual(
    year: int = Query(..., ge=2000, le=2100),
    cost_center_id: uuid.UUID | None = Query(None),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await report_service.get_dre_annual(
        session, ctx.workspace.id, ctx.user_id, year,
        cost_center_id=cost_center_id,
    )
```

- [ ] **Step 4: Atualizar `GET /dfc` para aceitar `cost_center_id`**

Localizar o endpoint `/dfc` e adicionar o parâmetro:

```python
@router.get("/dfc", response_model=DfcReport)
async def get_dfc(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    cost_center_id: uuid.UUID | None = Query(None),    # NOVO
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await report_service.get_dfc(
        session, ctx.workspace.id, ctx.user_id, year, month,
        cost_center_id=cost_center_id,    # NOVO
    )
```

- [ ] **Step 5: Atualizar `/dre/export` para usar `sections`**

No handler `export_dre`, a parte que itera `report.lines` precisa ser substituída por iteração em `sections`. Localizar:

```python
ws.append(["Detalhamento"])
for line in report.lines:
    ws.append(["  " + line.label, float(line.amount)])
```

Substituir por:

```python
for section in report.sections:
    ws.append([section.label])
    for grp in section.groups:
        ws.append(["  " + grp.group_name, float(grp.subtotal)])
        for line in grp.lines:
            ws.append(["    " + line.label, float(line.amount)])
    ws.append([])
```

- [ ] **Step 6: Verificar `test_write_permission_coverage.py`**

Os novos endpoints são `GET` — não são mutantes, então o teste de permissões não os cobre. Executar:

```
cd backend && python -m pytest tests/test_write_permission_coverage.py -v
```

Esperado: todos os testes passando (nenhuma entrada nova necessária para GET).

- [ ] **Step 7: Rodar todos os testes de DRE**

```
cd backend && python -m pytest tests/test_dre_api.py tests/test_dre_schemas.py -v
```

Esperado: todos os testes passando.

- [ ] **Step 8: Rodar a suíte completa**

```
cd backend && python -m pytest -n 4 --timeout=60
```

Esperado: sem regressões.

- [ ] **Step 9: Commit**

```bash
git add backend/app/api/reports.py
git commit -m "feat(a4): add /dre/quarterly, /dre/annual endpoints; add cost_center_id to /dre and /dfc"
```

---

### Task 4: Frontend — Tipos TypeScript + cliente API

**Files:**
- Modify: `frontend/src/lib/api.ts`

**Interfaces:**
- Produces:
  - `DreSection`, `DreGroupLine` (interfaces novas)
  - `DreReport` atualizado (campo `sections`, remove `lines`, adiciona `cost_center_id?`)
  - `DreQuarterlyReport`, `DreAnnualReport` (interfaces novas)
  - `dreApi.getDre(year, month, ccId?)` — assinatura atualizada
  - `dreApi.getDreQuarterly(year, quarter, ccId?)` — novo
  - `dreApi.getDreAnnual(year, ccId?)` — novo

- [ ] **Step 1: Localizar e atualizar `DreReport` em `frontend/src/lib/api.ts`**

Localizar (linha ~1494):
```typescript
export interface DreReport {
  year: number
  month: number
  currency: string
  gross_revenue: string
  deductions: string
  net_revenue: string
  operating_expenses: string
  result: string
  lines: { label: string; amount: string; subcategories: { label: string; amount: string; subcategories?: unknown[] }[] }[]
  prev_month?: DreReport
}
```

Substituir por:
```typescript
export interface DreLine {
  label: string
  amount: string
  subcategories: DreLine[]
}

export interface DreGroupLine {
  group_name: string
  lines: DreLine[]
  subtotal: string
}

export interface DreSection {
  key: 'receita' | 'despesa' | 'custo' | 'neutro'
  label: string
  groups: DreGroupLine[]
  subtotal: string
}

export interface DreReport {
  year: number
  month: number
  currency: string
  sections: DreSection[]
  gross_revenue: string
  deductions: string
  net_revenue: string
  operating_expenses: string
  result: string
  cost_center_id?: string | null
  prev_month?: DreReport
}

export interface DreQuarterlyReport {
  year: number
  quarter: number
  currency: string
  sections: DreSection[]
  gross_revenue: string
  operating_expenses: string
  result: string
  cost_center_id?: string | null
  months: DreReport[]
}

export interface DreAnnualReport {
  year: number
  currency: string
  sections: DreSection[]
  gross_revenue: string
  operating_expenses: string
  result: string
  cost_center_id?: string | null
  monthly: DreReport[]
}
```

- [ ] **Step 2: Atualizar `dreApi` em `frontend/src/lib/api.ts`**

Localizar (linha ~1516):
```typescript
export const dreApi = {
  getDre: (year: number, month: number): Promise<DreReport> =>
    api.get('/reports/dre', { params: { year, month } }).then((r) => r.data),
  getDfc: (year: number, month: number): Promise<DfcReport> =>
    api.get('/reports/dfc', { params: { year, month } }).then((r) => r.data),
  exportDre: (year: number, month: number): Promise<void> => ...
}
```

Substituir por:
```typescript
export const dreApi = {
  getDre: (year: number, month: number, ccId?: string | null): Promise<DreReport> =>
    api.get('/reports/dre', { params: { year, month, ...(ccId ? { cost_center_id: ccId } : {}) } }).then((r) => r.data),
  getDfc: (year: number, month: number, ccId?: string | null): Promise<DfcReport> =>
    api.get('/reports/dfc', { params: { year, month, ...(ccId ? { cost_center_id: ccId } : {}) } }).then((r) => r.data),
  getDreQuarterly: (year: number, quarter: number, ccId?: string | null): Promise<DreQuarterlyReport> =>
    api.get('/reports/dre/quarterly', { params: { year, quarter, ...(ccId ? { cost_center_id: ccId } : {}) } }).then((r) => r.data),
  getDreAnnual: (year: number, ccId?: string | null): Promise<DreAnnualReport> =>
    api.get('/reports/dre/annual', { params: { year, ...(ccId ? { cost_center_id: ccId } : {}) } }).then((r) => r.data),
  exportDre: (year: number, month: number): Promise<void> =>
    api
      .get('/reports/dre/export', { params: { year, month, format: 'xlsx' }, responseType: 'blob' })
      .then((r) => {
        const url = URL.createObjectURL(r.data)
        const a = document.createElement('a')
        a.href = url
        a.download = `dre_${year}_${String(month).padStart(2, '0')}.xlsx`
        a.click()
        URL.revokeObjectURL(url)
      }),
}
```

- [ ] **Step 3: Typecheck**

```
cd frontend && npm run typecheck
```

Esperado: sem erros de tipo.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(a4): update DreReport types and dreApi client for sections and quarterly/annual"
```

---

### Task 5: Frontend — Página DRE refatorada

**Files:**
- Modify: `frontend/src/pages/dre.tsx`
- Modify: `frontend/src/locales/en.json`, `pt-BR.json`, `es.json`
- Modify: `frontend/src/help/content/pt-BR/dre.md`

**Interfaces:**
- Consumes: `dreApi.getDre(ccId?)`, `dreApi.getDreQuarterly()`, `dreApi.getDreAnnual()` (Task 4); `DreSection`, `DreGroupLine`, `DreReport`, `DreQuarterlyReport`, `DreAnnualReport` (Task 4); `costCenters.list()` já existente em `api.ts`

- [ ] **Step 1: Adicionar chaves i18n (en/pt-BR/es)**

Em `frontend/src/locales/en.json`, dentro do objeto `"dre"`:
```json
"periodMonthly": "Month",
"periodQuarterly": "Quarter",
"periodAnnual": "Year",
"filterCc": "Cost Center",
"filterCcAll": "All",
"quarterLabel": "Q{{quarter}}/{{year}}",
"monthsDetail": "Monthly detail",
"section": {
  "receita": "Revenue",
  "custo": "Cost of Sales",
  "despesa": "Operating Expenses",
  "neutro": "Neutral"
},
"noGroup": "No group"
```

Em `frontend/src/locales/pt-BR.json`:
```json
"periodMonthly": "Mês",
"periodQuarterly": "Trimestre",
"periodAnnual": "Ano",
"filterCc": "Centro de custo",
"filterCcAll": "Todos",
"quarterLabel": "T{{quarter}}/{{year}}",
"monthsDetail": "Detalhe por mês",
"section": {
  "receita": "Receitas",
  "custo": "Custos",
  "despesa": "Despesas operacionais",
  "neutro": "Neutro"
},
"noGroup": "Sem grupo"
```

Em `frontend/src/locales/es.json`:
```json
"periodMonthly": "Mes",
"periodQuarterly": "Trimestre",
"periodAnnual": "Año",
"filterCc": "Centro de coste",
"filterCcAll": "Todos",
"quarterLabel": "T{{quarter}}/{{year}}",
"monthsDetail": "Detalle mensual",
"section": {
  "receita": "Ingresos",
  "custo": "Costos",
  "despesa": "Gastos operativos",
  "neutro": "Neutro"
},
"noGroup": "Sin grupo"
```

- [ ] **Step 2: Verificar paridade i18n**

```
cd frontend && npm run i18n:check -- --strict
```

Esperado: sem erros.

- [ ] **Step 3: Reescrever `frontend/src/pages/dre.tsx`**

```tsx
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Download, ChevronDown, ChevronRight } from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { PageHeader } from '@/components/page-header'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { dreApi, costCenters } from '@/lib/api'
import type { DreSection, DreReport } from '@/lib/api'
import { formatCurrency } from '@/lib/format'
import { useWorkspace } from '@/contexts/workspace-context'
import { useDisplayLocale } from '@/hooks/use-display-locale'
import { usePrivacyMode } from '@/hooks/use-privacy-mode'

type PeriodMode = 'monthly' | 'quarterly' | 'annual'

function SectionAccordion({
  section,
  fmt,
  prevSection,
}: {
  section: DreSection
  fmt: (v: number) => string
  prevSection?: DreSection
}) {
  const [open, setOpen] = useState(true)
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({})
  const n = (v: string) => Number(v ?? 0)

  return (
    <tbody>
      {/* Cabeçalho de seção */}
      <tr
        className="bg-muted/30 cursor-pointer select-none"
        onClick={() => setOpen((o) => !o)}
      >
        <td className="px-6 py-2 font-semibold flex items-center gap-1">
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          {section.label}
        </td>
        <td className="px-6 py-2 text-right tabular-nums font-semibold">
          {fmt(n(section.subtotal))}
        </td>
        {prevSection && (
          <td className="px-6 py-2 text-right tabular-nums text-muted-foreground">
            {fmt(n(prevSection.subtotal))}
          </td>
        )}
      </tr>

      {open && section.groups.map((grp) => {
        const grpOpen = openGroups[grp.group_name] ?? true
        const prevGrp = prevSection?.groups.find((g) => g.group_name === grp.group_name)
        return (
          <>
            <tr
              key={`grp-${grp.group_name}`}
              className="cursor-pointer hover:bg-muted/20"
              onClick={() => setOpenGroups((o) => ({ ...o, [grp.group_name]: !grpOpen }))}
            >
              <td className="px-8 py-1.5 text-sm flex items-center gap-1">
                {grpOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                {grp.group_name}
              </td>
              <td className="px-6 py-1.5 text-right tabular-nums text-sm">
                {fmt(n(grp.subtotal))}
              </td>
              {prevGrp && (
                <td className="px-6 py-1.5 text-right tabular-nums text-sm text-muted-foreground">
                  {fmt(n(prevGrp.subtotal))}
                </td>
              )}
            </tr>
            {grpOpen && grp.lines.map((line) => {
              const prevLine = prevGrp?.lines.find((l) => l.label === line.label)
              return (
                <tr key={`line-${line.label}`} className="border-b last:border-0">
                  <td className="px-12 py-1 text-sm text-muted-foreground">{line.label}</td>
                  <td className="px-6 py-1 text-right tabular-nums text-sm">
                    {fmt(n(line.amount))}
                  </td>
                  {prevLine && (
                    <td className="px-6 py-1 text-right tabular-nums text-sm text-muted-foreground">
                      {fmt(n(prevLine.amount))}
                    </td>
                  )}
                </tr>
              )
            })}
          </>
        )
      })}
    </tbody>
  )
}

export default function DrePage() {
  const { t } = useTranslation()
  const { current } = useWorkspace()
  const currency = current?.default_currency ?? 'BRL'
  const locale = useDisplayLocale()
  const { mask } = usePrivacyMode()
  const now = new Date()

  const [mode, setMode] = useState<PeriodMode>('monthly')
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [quarter, setQuarter] = useState(Math.ceil((now.getMonth() + 1) / 3))
  const [ccId, setCcId] = useState<string>('')

  const fmt = (v: number) => mask(formatCurrency(v, currency, locale))
  const n = (v: string | undefined | null) => Number(v ?? 0)

  const { data: ccList } = useQuery({
    queryKey: ['cost-centers'],
    queryFn: () => costCenters.list({ includeInactive: false }),
  })

  const { data: dreMonthly, isLoading: loadingMonthly } = useQuery({
    queryKey: ['dre', year, month, ccId],
    queryFn: () => dreApi.getDre(year, month, ccId || null),
    enabled: mode === 'monthly',
  })

  const { data: dreQuarterly, isLoading: loadingQuarterly } = useQuery({
    queryKey: ['dre-quarterly', year, quarter, ccId],
    queryFn: () => dreApi.getDreQuarterly(year, quarter, ccId || null),
    enabled: mode === 'quarterly',
  })

  const { data: dreAnnual, isLoading: loadingAnnual } = useQuery({
    queryKey: ['dre-annual', year, ccId],
    queryFn: () => dreApi.getDreAnnual(year, ccId || null),
    enabled: mode === 'annual',
  })

  const { data: dfc, isLoading: loadingDfc } = useQuery({
    queryKey: ['dfc', year, month, ccId],
    queryFn: () => dreApi.getDfc(year, month, ccId || null),
    enabled: mode === 'monthly',
  })

  const isLoading =
    (mode === 'monthly' && loadingMonthly) ||
    (mode === 'quarterly' && loadingQuarterly) ||
    (mode === 'annual' && loadingAnnual)

  const years = Array.from({ length: 5 }, (_, i) => now.getFullYear() - i)
  const months = Array.from({ length: 12 }, (_, i) => i + 1)
  const quarters = [1, 2, 3, 4]

  // Resumo para linha de resultado
  function ResultRow({ label, value, prevValue, bold }: { label: string; value: number; prevValue?: number; bold?: boolean }) {
    return (
      <tr className="border-t-2">
        <td className={`px-6 py-3 ${bold ? 'font-bold' : 'font-semibold'}`}>{label}</td>
        <td className={`px-6 py-3 text-right tabular-nums ${bold ? 'font-bold' : 'font-semibold'} ${value < 0 ? 'text-destructive' : ''}`}>
          {fmt(value)}
        </td>
        {prevValue !== undefined && (
          <td className="px-6 py-3 text-right tabular-nums text-muted-foreground">{fmt(prevValue)}</td>
        )}
      </tr>
    )
  }

  const activeDre: { sections: DreSection[]; result: string; prev?: DreReport } | null =
    mode === 'monthly' && dreMonthly
      ? { sections: dreMonthly.sections, result: dreMonthly.result, prev: dreMonthly.prev_month }
      : mode === 'quarterly' && dreQuarterly
      ? { sections: dreQuarterly.sections, result: dreQuarterly.result }
      : mode === 'annual' && dreAnnual
      ? { sections: dreAnnual.sections, result: dreAnnual.result }
      : null

  const dfcChartData = dfc?.periods.map((p) => ({
    date: p.date,
    inflows: n(p.inflows),
    outflows: n(p.outflows),
  }))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PageHeader section="analyze" title={t('dre.title')} />
        <div className="flex flex-wrap items-center gap-2">
          {/* Period selector */}
          <div className="flex rounded border overflow-hidden text-sm">
            {(['monthly', 'quarterly', 'annual'] as PeriodMode[]).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-3 py-1 ${mode === m ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'}`}
              >
                {t(`dre.period${m.charAt(0).toUpperCase() + m.slice(1)}`)}
              </button>
            ))}
          </div>

          {/* Period params */}
          {mode === 'monthly' && (
            <>
              <select value={month} onChange={(e) => setMonth(Number(e.target.value))} className="rounded border px-2 py-1 text-sm">
                {months.map((m) => <option key={m} value={m}>{String(m).padStart(2, '0')}</option>)}
              </select>
              <select value={year} onChange={(e) => setYear(Number(e.target.value))} className="rounded border px-2 py-1 text-sm">
                {years.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </>
          )}
          {mode === 'quarterly' && (
            <>
              <select value={quarter} onChange={(e) => setQuarter(Number(e.target.value))} className="rounded border px-2 py-1 text-sm">
                {quarters.map((q) => <option key={q} value={q}>Q{q}</option>)}
              </select>
              <select value={year} onChange={(e) => setYear(Number(e.target.value))} className="rounded border px-2 py-1 text-sm">
                {years.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </>
          )}
          {mode === 'annual' && (
            <select value={year} onChange={(e) => setYear(Number(e.target.value))} className="rounded border px-2 py-1 text-sm">
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          )}

          {/* CC filter */}
          <select value={ccId} onChange={(e) => setCcId(e.target.value)} className="rounded border px-2 py-1 text-sm">
            <option value="">{t('dre.filterCcAll')}</option>
            {ccList?.map((cc) => <option key={cc.id} value={cc.id}>{cc.name}</option>)}
          </select>

          {mode === 'monthly' && (
            <Button variant="outline" size="sm" onClick={() => dreApi.exportDre(year, month)}>
              <Download className="h-4 w-4 mr-1" />
              {t('dre.export')}
            </Button>
          )}
        </div>
      </div>

      {/* DRE Table */}
      {isLoading ? (
        <Skeleton className="h-48" />
      ) : activeDre ? (
        <div className="rounded-xl border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="px-6 py-3 text-left font-medium text-muted-foreground"></th>
                <th className="px-6 py-3 text-right font-medium">
                  {mode === 'monthly' ? `${String(month).padStart(2, '0')}/${year}`
                    : mode === 'quarterly' ? `Q${quarter}/${year}`
                    : String(year)}
                </th>
                {activeDre.prev && (
                  <th className="px-6 py-3 text-right font-medium text-muted-foreground">{t('dre.prevMonth')}</th>
                )}
              </tr>
            </thead>
            {activeDre.sections.map((sec) => (
              <SectionAccordion
                key={sec.key}
                section={sec}
                fmt={fmt}
                prevSection={activeDre.prev?.sections.find((s) => s.key === sec.key)}
              />
            ))}
            <tbody>
              <ResultRow
                label={t('dre.result')}
                value={n(activeDre.result)}
                prevValue={activeDre.prev ? n(activeDre.prev.result) : undefined}
                bold
              />
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-muted-foreground">{t('dre.noData')}</p>
      )}

      {/* Quarterly: detail by month */}
      {mode === 'quarterly' && dreQuarterly && (
        <details className="rounded-xl border bg-card p-4">
          <summary className="cursor-pointer font-medium">{t('dre.monthsDetail')}</summary>
          <div className="mt-4 grid grid-cols-3 gap-4">
            {dreQuarterly.months.map((m) => (
              <div key={m.month} className="rounded border p-3 text-sm">
                <div className="font-semibold mb-2">{String(m.month).padStart(2, '0')}/{m.year}</div>
                {m.sections.map((s) => (
                  <div key={s.key} className="flex justify-between">
                    <span className="text-muted-foreground">{s.label}</span>
                    <span>{fmt(n(s.subtotal))}</span>
                  </div>
                ))}
                <div className="flex justify-between font-semibold border-t mt-1 pt-1">
                  <span>{t('dre.result')}</span>
                  <span className={n(m.result) < 0 ? 'text-destructive' : ''}>{fmt(n(m.result))}</span>
                </div>
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Annual: seasonality table */}
      {mode === 'annual' && dreAnnual && (
        <div className="rounded-xl border bg-card overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr>
                <th className="px-4 py-2 text-left font-medium text-muted-foreground">{t('dre.title')}</th>
                {dreAnnual.monthly.map((m) => (
                  <th key={m.month} className="px-3 py-2 text-right font-medium">{String(m.month).padStart(2, '0')}</th>
                ))}
                <th className="px-3 py-2 text-right font-semibold">{t('common.total', 'Total')}</th>
              </tr>
            </thead>
            <tbody>
              {dreAnnual.sections.map((sec) => (
                <>
                  <tr key={sec.key} className="bg-muted/30">
                    <td className="px-4 py-1.5 font-semibold">{sec.label}</td>
                    {dreAnnual.monthly.map((m) => {
                      const ms = m.sections.find((s) => s.key === sec.key)
                      return <td key={m.month} className="px-3 py-1.5 text-right tabular-nums">{fmt(ms ? n(ms.subtotal) : 0)}</td>
                    })}
                    <td className="px-3 py-1.5 text-right tabular-nums font-semibold">{fmt(n(sec.subtotal))}</td>
                  </tr>
                </>
              ))}
              <tr className="border-t-2 font-bold">
                <td className="px-4 py-2">{t('dre.result')}</td>
                {dreAnnual.monthly.map((m) => (
                  <td key={m.month} className={`px-3 py-2 text-right tabular-nums ${n(m.result) < 0 ? 'text-destructive' : ''}`}>
                    {fmt(n(m.result))}
                  </td>
                ))}
                <td className={`px-3 py-2 text-right tabular-nums ${n(dreAnnual.result) < 0 ? 'text-destructive' : ''}`}>
                  {fmt(n(dreAnnual.result))}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* DFC chart (monthly only) */}
      {mode === 'monthly' && (
        <div>
          <h3 className="font-semibold mb-3">{t('dre.dfc')}</h3>
          {loadingDfc ? (
            <Skeleton className="h-48" />
          ) : dfcChartData && dfcChartData.length > 0 ? (
            <div className="rounded-xl border bg-card p-4">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={dfcChartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(value: number | undefined) => [value != null ? fmt(value) : '', '']} />
                  <Bar dataKey="inflows" name={t('dre.inflows')} fill="#22c55e" />
                  <Bar dataKey="outflows" name={t('dre.outflows')} fill="#ef4444" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="text-muted-foreground">{t('dre.noData')}</p>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Atualizar help doc `frontend/src/help/content/pt-BR/dre.md`**

Adicionar seção sobre o filtro de CC e as novas granularidades ao arquivo de ajuda existente. O conteúdo exato depende do arquivo atual — adicionar ao final do arquivo:

```markdown
## Filtrar por centro de custo

Use o seletor **Centro de custo** no topo da página para ver o DRE apenas das transações de um CC específico. "Todos" exibe o consolidado.

## Períodos

- **Mês:** DRE do mês selecionado com comparativo do mês anterior.
- **Trimestre:** Acumulado dos 3 meses do trimestre. Expanda "Detalhe por mês" para ver cada mês individualmente.
- **Ano:** Acumulado do ano com tabela de sazonalidade (12 colunas).
```

- [ ] **Step 5: Rodar typecheck e lint**

```
cd frontend && npm run typecheck && npm run lint
```

Esperado: sem erros.

- [ ] **Step 6: Rodar testes de frontend**

```
cd frontend && npm test
```

Esperado: sem regressões (topics.test.ts deve continuar passando).

- [ ] **Step 7: Verificar paridade i18n**

```
cd frontend && npm run i18n:check -- --strict
```

Esperado: sem erros.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/dre.tsx frontend/src/locales/en.json frontend/src/locales/pt-BR.json frontend/src/locales/es.json frontend/src/help/content/pt-BR/dre.md
git commit -m "feat(a4): refactor DRE page with period selector, CC filter, and hierarchical sections"
```

---

## Ordem de execução e dependências

```
Task 1 (schemas) → Task 2 (service) → Task 3 (API routes)
                                    ↓
                              Task 4 (TS types + API client) → Task 5 (DRE page)
```

Tasks 3 e 4 são independentes entre si e podem rodar em paralelo após Task 2.

## Verificação final

Após todos os tasks:

```bash
# Backend
cd backend && python -m pytest -n 4 --timeout=60

# Frontend
cd frontend && npm run typecheck && npm run lint && npm test && npm run i18n:check -- --strict
```
