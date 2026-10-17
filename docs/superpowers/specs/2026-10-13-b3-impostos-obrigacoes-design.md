# B3 — Impostos e obrigações: obrigações fiscais no forecast + retenções na fatura

**Data:** 2026-10-13
**Item do plano:** ENTERPRISE.md § B3
**Prioridade:** P2 · **Esforço:** M (2–3 semanas)

## Contexto

O SyncroFin já tem recorrências genéricas (`RecurringTransaction`), previsão de caixa via AR/AP
(`ar_ap_service.get_forecast`), faturas com `tax_total` (imposto cobrado do cliente) e categorias
fiscais pré-configuradas (`biz_tax_simples`, `biz_tax_revenue`, `biz_tax_income`, `biz_tax_other`).

O que falta:
1. **Obrigações fiscais** (DAS, DARF, ISS, INSS) como entradas tipadas na previsão de caixa.
2. **Retenções na fatura** (IRRF, ISS, PIS, COFINS, CSLL retidos pelo cliente) — a "tabela T6"
   referenciada nos comentários de `models/invoice.py:229` e `models/payee.py:104`.

## Decisões de design

| # | Decisão | Escolha |
|---|---------|---------|
| 1 | Obrigações: modelo novo vs. estender RecurringTransaction | **Estender** — campo discriminador `tax_obligation_type` |
| 2 | Retenções: campo no invoice vs. tabela filha | **Tabela filha** `invoice_withholdings` (N retenções por fatura) |
| 3 | Forecast: projetar bruto ou líquido para receivable | **Líquido** (`net_receivable = total − total_withheld`) |
| 4 | Permissões novas | **Nenhuma** — reusa `planning.write` e `invoices.write` |

## 1. Modelo de dados

### 1.1 Migração 115 — campos em `recurring_transactions`

```sql
ALTER TABLE recurring_transactions
  ADD COLUMN tax_obligation_type VARCHAR(30),
  ADD COLUMN tax_reference_code  VARCHAR(20),
  ADD COLUMN competence_offset_months SMALLINT NOT NULL DEFAULT 0;

-- Índice para queries filtradas
CREATE INDEX ix_recurring_tx_tax_type
  ON recurring_transactions (workspace_id, tax_obligation_type)
  WHERE tax_obligation_type IS NOT NULL;
```

**Valores válidos de `tax_obligation_type`:**

| Valor | Descrição | Frequência típica | Dia típico |
|-------|-----------|-------------------|------------|
| `das` | DAS do Simples Nacional | Mensal | 20 |
| `darf_irpj` | DARF — IRPJ | Trimestral | Último dia útil do mês seguinte |
| `darf_csll` | DARF — CSLL | Trimestral | Último dia útil do mês seguinte |
| `darf_irrf` | DARF — IRRF retido | Mensal | 20 |
| `darf_pis_cofins` | DARF — PIS/COFINS | Mensal | 25 |
| `iss` | ISS municipal | Mensal | Varia por município (5–15) |
| `inss` | INSS patronal/empregador | Mensal | 20 |
| `icms` | ICMS estadual | Mensal | Varia por UF |
| `other` | Outro tributo | Configurável | Configurável |

**`tax_reference_code`** — código da receita para DARFs (ex.: `1708` = IRRF sobre serviços,
`2372` = CSLL, `5856` = PIS/COFINS importação). Informativo; não afeta lógica.

**`competence_offset_months`** — quantos meses depois da competência o vencimento cai.
Ex.: DAS de setembro vence em outubro → offset = 1. Default 0 para obrigações que vencem no
próprio mês. Usado apenas para exibição ("competência: set/2026") a partir da data de vencimento.

### 1.2 Migração 116 — tabela `invoice_withholdings`

```sql
CREATE TABLE invoice_withholdings (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id    UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  workspace_id  UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  tax_type      VARCHAR(20) NOT NULL,   -- irrf, iss, pis, cofins, csll, inss, other
  rate          NUMERIC(7,4),           -- alíquota (ex.: 1.5000 = 1,5%)
  base_amount   NUMERIC(15,2) NOT NULL, -- base de cálculo
  withheld_amount NUMERIC(15,2) NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

  CONSTRAINT uq_withholding_per_type UNIQUE (invoice_id, tax_type),
  CONSTRAINT ck_withholding_tax_type CHECK (
    tax_type IN ('irrf', 'iss', 'pis', 'cofins', 'csll', 'inss', 'other')
  ),
  CONSTRAINT ck_withholding_positive CHECK (withheld_amount > 0)
);

CREATE INDEX ix_invoice_withholdings_invoice ON invoice_withholdings (invoice_id);
CREATE INDEX ix_invoice_withholdings_workspace ON invoice_withholdings (workspace_id);
```

**Semântica:** retenção é o que o cliente *desconta* do pagamento e recolhe por nós.
`withheld_amount` reduz o caixa recebido sem reduzir o saldo devedor da fatura.

- `total` da fatura (o que o cliente deve) permanece intacto.
- `net_receivable` = `total − sum(withheld_amount)` — o que efetivamente entra no caixa.
- A diferença (`withheld_amount`) é o que o cliente recolheu como substituto tributário.

## 2. Backend

### 2.1 Modelo `InvoiceWithholding`

Arquivo: `backend/app/models/invoice_withholding.py`

```python
class InvoiceWithholding(Base):
    __tablename__ = "invoice_withholdings"

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("invoices.id", ondelete="CASCADE"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID, ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    tax_type: Mapped[str] = mapped_column(String(20))
    rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 4), nullable=True)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    withheld_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped["Invoice"] = relationship(back_populates="withholdings")
```

**Alterações em `Invoice`:**
- Nova relationship: `withholdings: Mapped[list["InvoiceWithholding"]] = relationship(...)`
- Nova propriedade: `total_withheld` → `sum(w.withheld_amount for w in self.withholdings)`
- Nova propriedade: `net_receivable` → `self.total - self.total_withheld`

### 2.2 Alterações em `RecurringTransaction`

3 novos campos no modelo (nullable, sem impacto em recorrências existentes).
CheckConstraint para valores válidos de `tax_obligation_type`.

### 2.3 Schemas

**`recurring_transaction.py` — campos novos nos schemas Create/Update/Read:**
- `tax_obligation_type: Optional[str]`
- `tax_reference_code: Optional[str]`
- `competence_offset_months: int = 0`

**`invoice_withholding.py` — novos schemas:**
- `WithholdingCreate`: `tax_type`, `rate` (opt), `base_amount`, `withheld_amount`
- `WithholdingRead`: todos os campos + `id`
- `WithholdingUpdate`: todos opcionais

**`invoice.py` — campos no Read:**
- `withholdings: list[WithholdingRead]`
- `total_withheld: Decimal`
- `net_receivable: Decimal`

### 2.4 API — Obrigações fiscais

Novos endpoints em `api/tax_obligations.py`:

| Método | Rota | Descrição | Permissão |
|--------|------|-----------|-----------|
| `GET` | `/api/tax-obligations` | Lista recorrências com `tax_obligation_type IS NOT NULL` | `export.read` |
| `GET` | `/api/tax-obligations/summary` | Total mensal projetado por tipo de obrigação | `export.read` |
| `GET` | `/api/tax-obligations/forecast` | Projeção nos próximos N meses (buckets) | `export.read` |

Não há CRUD separado — a criação/edição de obrigações usa os endpoints de
`/api/recurring-transactions` com `tax_obligation_type` preenchido.

### 2.5 API — Retenções na fatura

Endpoints em `api/invoices.py` (aninhados na fatura):

| Método | Rota | Descrição | Permissão |
|--------|------|-----------|-----------|
| `POST` | `/api/invoices/{id}/withholdings` | Adiciona retenção | `invoices.write` |
| `PATCH` | `/api/invoices/{id}/withholdings/{wid}` | Edita retenção | `invoices.write` |
| `DELETE` | `/api/invoices/{id}/withholdings/{wid}` | Remove retenção | `invoices.write` |

Validação: `sum(withheld_amount) ≤ invoice.total`; fatura `void`/`uncollectible` não aceita retenção.

Também aceito `withholdings` no body de `POST /api/invoices` e `PATCH /api/invoices/{id}` para
criação/edição inline (como já é feito com `lines`).

### 2.6 Integração no forecast

**`ar_ap_service.get_forecast`:**

Além dos claims de faturas, agora também chama
`recurring_transaction_service.get_occurrences_in_range` filtrando por
`tax_obligation_type IS NOT NULL` e adiciona cada ocorrência como claim `payable`.

**`invoice_forecast_service.claims_in_range`:**

Para faturas `receivable` com retenções, projeta `net_receivable` (total − withheld) em vez de
`total`. Implementado via subquery que soma `invoice_withholdings.withheld_amount` por fatura.

**Schema `ForecastBucket`:**

Ganha campo opcional `taxes: Decimal` (total de obrigações fiscais no período).
`payable` continua sendo o total de faturas a pagar; `taxes` é separado para visibilidade.
`net = receivable − payable − taxes`.

### 2.7 Integração na conciliação

**`reconciliation_policy.withholding_ratios`:**

Deixa de retornar lista vazia. Nova lógica:

```python
def withholding_ratios(jurisdiction: str | None) -> list[Decimal]:
    """Alíquotas comuns de retenção no Brasil."""
    if jurisdiction and jurisdiction.upper() == "BR":
        return [
            Decimal("0.985"),   # IRRF 1,5%
            Decimal("0.95"),    # ISS 5%
            Decimal("0.9575"),  # PIS+COFINS 4,25% (0,65+3,60 cumulativo)
            Decimal("0.99"),    # CSLL 1%
            Decimal("0.89"),    # INSS 11%
        ]
    return []
```

Isso ativa a estratégia `same_client_net_of_withholding` que já existe no motor de conciliação,
permitindo que pagamentos com valor menor sejam automaticamente linkados a faturas quando a
diferença corresponde a uma retenção conhecida.

### 2.8 Auditoria

O listener de auditoria (`AuditEvent`) já cobre automaticamente novos modelos via
`after_flush`. `InvoiceWithholding` será incluído no set de modelos auditados (como as
`InvoiceLine` e `InvoiceAllocation` já são).

## 3. Frontend

### 3.1 Página/aba de obrigações fiscais

**Opção escolhida:** nova aba "Impostos" dentro da página de recorrências (`recurring.tsx`).

Componentes:
- `TaxObligationsList` — lista filtrada de recorrências fiscais, com colunas: tipo, descrição,
  valor, frequência, próximo vencimento, competência referente
- `TaxObligationDialog` — dialog de criação/edição com:
  - Select de tipo de obrigação (DAS, DARF IRPJ, DARF CSLL, etc.)
  - Código da receita (visível para DARFs)
  - Valor, frequência (default mensal), dia do vencimento
  - Conta de pagamento, categoria (pré-selecionada conforme tipo)
  - Offset de competência
- `TaxObligationSummary` — card com total mensal de impostos projetados

### 3.2 Retenções no detalhe da fatura

Nova seção em `invoice-detail.tsx`, visível apenas para faturas `receivable`:

- Tabela de retenções: tipo (IRRF, ISS, PIS, COFINS, CSLL, INSS), alíquota, base, valor retido
- Botão "Adicionar retenção" abre row editável inline ou mini-dialog
- Resumo: `Bruto: R$ X.XXX | Retenções: −R$ Y.YYY | Líquido: R$ Z.ZZZ`
- A seção aparece recolhida quando não há retenções, com link "Adicionar retenções"

### 3.3 Forecast com impostos

Alterações em `cash-flow-forecast.tsx`:
- Nova coluna "Impostos" na tabela de forecast
- Barra de impostos no gráfico (cor distinta, ex.: laranja)
- `net` = receivable − payable − taxes

### 3.4 Help topic

Novo tópico em `frontend/src/help/topics.ts` e conteúdo em
`frontend/src/help/content/pt-BR/impostos.md` cobrindo:
- Como cadastrar obrigações fiscais
- Como configurar retenções na fatura
- Como os impostos aparecem na previsão de caixa

## 4. i18n

Chaves novas nos três idiomas (`en`, `pt-BR`, `es`):

```json
{
  "taxObligations": "Obrigações Fiscais",
  "taxObligationType": "Tipo de obrigação",
  "taxObligationTypes": {
    "das": "DAS — Simples Nacional",
    "darf_irpj": "DARF — IRPJ",
    "darf_csll": "DARF — CSLL",
    "darf_irrf": "DARF — IRRF",
    "darf_pis_cofins": "DARF — PIS/COFINS",
    "iss": "ISS",
    "inss": "INSS",
    "icms": "ICMS",
    "other": "Outro tributo"
  },
  "taxReferenceCode": "Código da receita",
  "competenceMonth": "Competência",
  "competenceOffset": "Vencimento após competência",
  "withholdings": "Retenções",
  "withholdingTypes": {
    "irrf": "IRRF",
    "iss": "ISS retido",
    "pis": "PIS retido",
    "cofins": "COFINS retida",
    "csll": "CSLL retida",
    "inss": "INSS retido",
    "other": "Outra retenção"
  },
  "addWithholding": "Adicionar retenção",
  "grossTotal": "Total bruto",
  "totalWithheld": "Total retido",
  "netReceivable": "Líquido a receber",
  "taxForecast": "Impostos projetados",
  "monthlySummary": "Resumo mensal de impostos"
}
```

## 5. Testes

### 5.1 Backend

**`test_tax_obligations.py`:**
- CRUD de recorrência com `tax_obligation_type` preenchido
- Projeção de obrigações no forecast via `/api/tax-obligations/forecast`
- Integração no AR/AP forecast (obrigações aparecem como payable)
- Validação de `tax_obligation_type` (valor inválido → 422)

**`test_invoice_withholdings.py`:**
- CRUD de retenções via endpoints aninhados
- Cálculo de `total_withheld` e `net_receivable`
- Validação: `sum(withheld) > total` → 422
- Retenção em fatura void → 422
- Impacto no forecast: receivable projeta net_receivable
- Inline creation: retenções no body de POST/PATCH de fatura

**`test_reconciliation_withholding.py`:**
- `withholding_ratios("BR")` retorna lista não vazia
- Motor de conciliação auto-linka pagamento com retenção IRRF (teste existente, agora ativado)

**`test_write_permission_coverage.py`:**
- Novas rotas na allowlist

### 5.2 Frontend

- Testes de componente para `TaxObligationDialog`, `TaxObligationsList`
- Testes de seção de retenções no detalhe da fatura
- `topics.test.ts` cobre o novo tópico de help

## 6. Arquivos afetados (resumo)

### Novos
- `backend/alembic/versions/115_tax_obligation_fields.py`
- `backend/alembic/versions/116_invoice_withholdings.py`
- `backend/app/models/invoice_withholding.py`
- `backend/app/schemas/invoice_withholding.py`
- `backend/app/api/tax_obligations.py`
- `backend/tests/test_tax_obligations.py`
- `backend/tests/test_invoice_withholdings.py`
- `frontend/src/help/content/pt-BR/impostos.md`

### Modificados
- `backend/app/models/recurring_transaction.py` — 3 campos novos
- `backend/app/models/invoice.py` — relationship + propriedades
- `backend/app/models/__init__.py` — import do novo modelo
- `backend/app/schemas/recurring_transaction.py` — campos opcionais
- `backend/app/schemas/invoice.py` — withholdings no Read
- `backend/app/schemas/ar_ap.py` — `taxes` no ForecastBucket
- `backend/app/services/ar_ap_service.py` — obrigações fiscais no forecast
- `backend/app/services/invoice_forecast_service.py` — net_receivable
- `backend/app/services/invoice_service.py` — withholdings inline
- `backend/app/services/reconciliation_policy.py` — withholding_ratios BR
- `backend/app/main.py` — registrar router
- `backend/tests/test_write_permission_coverage.py` — allowlist
- `frontend/src/pages/recurring.tsx` — aba Impostos
- `frontend/src/pages/invoice-detail.tsx` — seção Retenções
- `frontend/src/components/ar-ap/cash-flow-forecast.tsx` — coluna Impostos
- `frontend/src/lib/api.ts` — novos endpoints
- `frontend/src/help/topics.ts` — novo tópico
- `frontend/src/locales/{en,pt-BR,es}.json` — chaves novas
- `frontend/src/types/index.ts` — tipos novos
