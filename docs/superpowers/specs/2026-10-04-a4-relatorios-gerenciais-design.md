# A4 — Relatórios Gerenciais Integrados: Design

## Contexto

O SyncroFin Enterprise já possui um DRE básico (`/api/reports/dre`) que agrupa transações por nome de
categoria e retorna campos fixos (`gross_revenue`, `operating_expenses`, `result`). Com A2 (plano de
contas hierárquico) e A3 (centros de custo) no ar, este spec refatora o DRE para usar a hierarquia
real e adiciona granularidade trimestral e anual.

A4b (comparativo orçado × realizado por CC) foi adiado: o modelo de orçamento atual é por categoria
individual e não suporta agregação por hierarquia. Ficará como sub-projeto separado.

---

## Decisões de design

| Pergunta | Decisão |
|----------|---------|
| Estrutura do DRE | Híbrida: seções por `natureza` (Receitas / Custos / Despesas / Neutro) com grupos de categoria dentro de cada seção |
| Fallback sem natureza | `tx.type == "credit"` → receita; `"debit"` → despesa |
| Escopo de CC | Filtro simples (`?cost_center_id=`); sem comparativo CC × orçamento |
| Granularidades | Mensal (existente) + Trimestral + Anual |
| Estratégia de endpoints | **Opção B — endpoints separados** por granularidade |

---

## Schemas

### Tipos novos

```python
class DreLine(BaseModel):          # já existe — categoria leaf
    label: str
    amount: Decimal
    subcategories: list[DreLine] = []

class DreGroupLine(BaseModel):     # novo — grupo de categoria
    group_name: str
    lines: list[DreLine]           # categorias dentro do grupo
    subtotal: Decimal

class DreSection(BaseModel):       # novo — seção por natureza
    key: str                       # "receita" | "despesa" | "custo" | "neutro"
    label: str                     # "Receitas", "Custos", etc.
    groups: list[DreGroupLine]
    subtotal: Decimal
```

### `DreReport` refatorado (endpoint mensal)

```python
class DreReport(BaseModel):
    year: int
    month: int
    currency: str
    sections: list[DreSection]    # novo campo principal
    gross_revenue: Decimal        # mantido para compatibilidade
    deductions: Decimal
    net_revenue: Decimal
    operating_expenses: Decimal
    result: Decimal
    cost_center_id: uuid.UUID | None
    prev_month: DreReport | None
```

### `DreQuarterlyReport` (novo)

```python
class DreQuarterlyReport(BaseModel):
    year: int
    quarter: int                   # 1–4
    currency: str
    sections: list[DreSection]     # acumulado dos 3 meses
    gross_revenue: Decimal
    operating_expenses: Decimal
    result: Decimal
    cost_center_id: uuid.UUID | None
    months: list[DreReport]        # os 3 meses individuais (para detalhamento)
```

### `DreAnnualReport` (novo)

```python
class DreAnnualReport(BaseModel):
    year: int
    currency: str
    sections: list[DreSection]     # acumulado anual
    gross_revenue: Decimal
    operating_expenses: Decimal
    result: Decimal
    cost_center_id: uuid.UUID | None
    monthly: list[DreReport]       # 12 meses (para tabela de sazonalidade)
```

---

## API

### Endpoints

| Método | Rota | Parâmetros | Schema de resposta |
|--------|------|-----------|-------------------|
| GET | `/api/reports/dre` | `year`, `month`, `cost_center_id?` | `DreReport` |
| GET | `/api/reports/dre/quarterly` | `year`, `quarter` (1–4), `cost_center_id?` | `DreQuarterlyReport` |
| GET | `/api/reports/dre/annual` | `year`, `cost_center_id?` | `DreAnnualReport` |
| GET | `/api/reports/cash-flow` | (parâmetros existentes), `cost_center_id?` | (schema inalterado) |

**Permissão:** `require_permission("reports.view")` em todos.

**Workspace isolation para CC:** `_ensure_cost_center_in_workspace(session, cost_center_id, workspace_id)` —
levanta `HTTPException(404, "cost_center_not_found")` se o CC não pertencer ao workspace do usuário.
O mesmo helper já existe em `transaction_service.py` e `budget_service.py`.

### Algoritmo de construção de seções

```python
def build_dre_sections(
    transactions: list[Transaction],
    groups_by_id: dict[uuid.UUID, CategoryGroup],
) -> list[DreSection]:
    # 1. Classificar cada transação em (natureza, grupo_nome, categoria_label, amount)
    buckets: dict[str, dict[str, dict[str, Decimal]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(Decimal))
    )
    for tx in transactions:
        cat = tx.category
        group = groups_by_id.get(cat.group_id) if cat and cat.group_id else None
        natureza = (
            group.effective_natureza if group and group.effective_natureza else
            ("receita" if tx.type == "credit" else "despesa")
        )
        group_key = group.name if group else "_sem_grupo"
        cat_label = cat.name if cat else tx.description or "Sem categoria"
        buckets[natureza][group_key][cat_label] += tx.amount

    # 2. Montar DreSection / DreGroupLine / DreLine
    SECTION_ORDER = ["receita", "custo", "despesa", "neutro"]
    SECTION_LABELS = {
        "receita": "Receitas",
        "custo": "Custos",
        "despesa": "Despesas operacionais",
        "neutro": "Neutro",
    }
    sections = []
    for nat in SECTION_ORDER:
        if nat not in buckets:
            continue
        groups = []
        for grp_name, cats in buckets[nat].items():
            lines = [DreLine(label=k, amount=v) for k, v in cats.items()]
            groups.append(DreGroupLine(
                group_name=grp_name if grp_name != "_sem_grupo" else "Sem grupo",
                lines=lines,
                subtotal=sum(l.amount for l in lines),
            ))
        sections.append(DreSection(
            key=nat,
            label=SECTION_LABELS[nat],
            groups=groups,
            subtotal=sum(g.subtotal for g in groups),
        ))
    return sections
```

### Agregação trimestral / anual

- **Trimestral:** chama `get_dre_month()` para cada um dos 3 meses do trimestre e soma os valores
  por `(natureza, grupo, categoria)`. Retorna `months: list[DreReport]` com os meses individuais.
- **Anual:** chama `get_dre_month()` para os 12 meses e agrega da mesma forma. Retorna
  `monthly: list[DreReport]` para a tabela de sazonalidade no frontend.

O filtro de CC é passado em todas as chamadas internas a `get_dre_month()`.

---

## Frontend

### Arquivos modificados

| Arquivo | O que muda |
|---------|-----------|
| `frontend/src/pages/dre.tsx` | Seletor de período (Mês/Trimestre/Ano) + filtro de CC; renderização hierárquica por `sections[]`; accordion seção → grupo → categoria |
| `frontend/src/lib/api.ts` | `reports.dre()` ganha `ccId?`; novos métodos `reports.dreQuarterly(year, quarter, ccId?)` e `reports.dreAnnual(year, ccId?)` |
| `frontend/src/types/index.ts` | `DreSection`, `DreGroupLine`; `DreReport.sections`; `DreQuarterlyReport`; `DreAnnualReport` |
| `frontend/src/locales/en.json`, `pt-BR.json`, `es.json` | Chaves `dre.period.*`, `dre.section.*` (paridade obrigatória en/pt-BR/es) |
| `frontend/src/help/content/pt-BR/dre.md` | Atualiza manual: filtro CC, períodos trimestral/anual |

**Sem nova rota** — tudo vive em `/dre` com estado local React.

### Layout da página

```
┌─ DRE ─────────────────────────────────────────────────┐
│ [Mês] [Trimestre] [Ano]     Filtrar CC: [Todos ▼]     │
│ ← Jan 2026  |  Fev 2026 →  (modo mensal)             │
├───────────────────────────────────────────────────────┤
│ ▼ Receitas                             R$ 15.000      │
│     ▶ Serviços                          R$ 7.000      │
│         Consultoria                     R$ 5.000      │
│         Suporte                         R$ 2.000      │
│     ▶ Produtos                          R$ 8.000      │
│ ─────────────────────────────────────────────────     │
│ ▼ Custos                                R$ 3.000      │
│ ▼ Despesas operacionais                 R$ 1.900      │
│ ═════════════════════════════════════════════════     │
│   Resultado                            R$ 10.100      │
└───────────────────────────────────────────────────────┘
```

Modo trimestral: acumulado no topo + seção colapsável "Ver por mês" com 3 colunas.
Modo anual: acumulado no topo + tabela de sazonalidade com 12 colunas.

O comparativo `prev_month` continua no modo mensal (coluna lateral).

---

## O que NÃO está no escopo (A4b — futuro)

- Comparativo orçado × realizado por CC
- Agregação de orçamentos por natureza/grupo
- Tabela de variação orçado × realizado

Motivo: o modelo de `Budget` atual é por categoria individual. Suportar agregação por hierarquia
exige trabalho separado no `budget_service.py` e novas migrações. Ficará como sub-projeto A4b.

---

## Testes

### Backend

- `test_dre_sections_natureza` — transações de naturezas diferentes aparecem em seções corretas
- `test_dre_fallback_no_natureza` — categoria sem grupo/natureza cai em receita/despesa por `tx.type`
- `test_dre_cost_center_filter` — com `cost_center_id`, só transações desse CC aparecem
- `test_dre_cost_center_foreign_workspace` — CC de outro workspace → 404
- `test_dre_quarterly_sums_three_months` — valores trimestrais = soma dos 3 meses individuais
- `test_dre_annual_has_12_months` — `monthly` tem exatamente 12 entradas

### Frontend

- Renderização das seções com acordeão (smoke test via mock)
- Seletor de período troca o endpoint chamado
- Filtro de CC passa `cost_center_id` na query

---

## Compatibilidade

Os campos herdados `gross_revenue`, `deductions`, `net_revenue`, `operating_expenses`, `result` são
mantidos em `DreReport` para não quebrar clientes existentes. O campo `lines` (antigo) é removido —
era `list[DreLine]` nunca renderizado no frontend.
