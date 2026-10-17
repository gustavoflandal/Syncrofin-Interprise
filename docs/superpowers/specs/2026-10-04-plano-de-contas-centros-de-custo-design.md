# Plano de Contas Hierárquico + Centros de Custo (P1 da Fase 2)

## Objetivo

Estender o SyncroFin Enterprise com (A2) hierarquia de plano de contas de 3 níveis e campo
`natureza` nos grupos de categoria, e (A3) centros de custo como dimensão opcional em
transações, splits, orçamentos e relatórios.

## Posicionamento

Gestão financeira para PMEs + exportação ao contador. Sem partidas dobradas. O plano de contas
serve para categorizar lançamentos e gerar relatórios (DRE por natureza, filtros por CC),
não para escrituração contábil completa.

---

## Decisões de design

| Questão | Decisão |
|---------|---------|
| Relação com categorias existentes | Evolução (Opção A) — campos novos nullable no `CategoryGroup`; zero breaking change |
| Profundidade da hierarquia | 3 níveis: Grupo raiz (depth=0) → Subgrupo (depth=1) → Categoria (folha) |
| Valores de natureza | 4 simples: `receita`, `despesa`, `custo`, `neutro` |
| Obrigatoriedade de CC | Sempre opcional; nenhuma política de workspace neste ciclo |
| CC em splits | Sim — cada split pode ter CC diferente |
| CC em orçamentos | Sim — criação e filtro |

---

## A2 — Plano de contas hierárquico

### Mudanças no modelo `CategoryGroup`

```python
parent_id:  Optional[UUID]  FK → category_groups.id  ON DELETE SET NULL
code:       Optional[str(20)]   # código livre: "4", "4.1", "4.1.01", "REC-OP"
natureza:   Optional[str(20)]   # receita | despesa | custo | neutro
depth:      int  NOT NULL  DEFAULT 0
```

**Regras de negócio:**
- `depth=0, parent_id=NULL` → grupo raiz (classe ou grupo simples sem classe acima — backward-compatible)
- `depth=1, parent_id → grupo raiz` → subgrupo
- Max profundidade: 1 (subgrupo não pode ter filhos; validado no service)
- Herança de natureza: se o subgrupo não tem `natureza`, usa a do pai em tempo de query
- Código único por workspace (validação no service; `409 CONFLICT` em duplicata)
- Ciclos proibidos: `parent.parent_id IS NOT NULL` → `400 BAD_REQUEST`

**Grupos existentes:** recebem `parent_id=NULL`, `code=NULL`, `natureza=NULL`, `depth=0`
— comportamento idêntico ao atual.

### Mudanças no service `category_group_service.py`

- `create_group(parent_id?, code?, natureza?)` — calcula `depth` automaticamente; valida regras acima
- `update_group(id, ...)` — proíbe mover grupo raiz para subgrupo se já tiver filhos
- `get_tree(workspace_id)` → lista hierárquica (raiz → filhos → categorias folha) via `selectinload`
- `get_effective_natureza(group)` → natureza própria ou herdada do pai

### Mudanças no DRE service

Quando `natureza` está definida na cadeia de grupo da categoria, o DRE usa natureza em vez
de `type`:

| natureza | Linha DRE |
|----------|-----------|
| `receita` | Receita bruta |
| `custo` | CMV / Custo |
| `despesa` | Despesa operacional |
| `neutro` | Excluído do DRE (igual a `treat_as_transfer`) |
| `NULL` (sem natureza) | Fallback: `credit` = receita, `debit` = despesa (comportamento atual) |

### API — rotas existentes afetadas

- `GET /api/category-groups` → inclui `parent_id`, `code`, `natureza`, `depth`, `children[]`
- `POST /api/category-groups` e `PATCH /api/category-groups/{id}` → aceitam campos novos
- Nenhuma rota nova necessária para A2

### Migração

```
093_chart_of_accounts.py
```

```sql
ALTER TABLE category_groups
  ADD COLUMN parent_id UUID REFERENCES category_groups(id) ON DELETE SET NULL,
  ADD COLUMN code VARCHAR(20),
  ADD COLUMN natureza VARCHAR(20),
  ADD COLUMN depth SMALLINT NOT NULL DEFAULT 0;

CREATE INDEX ix_category_groups_parent_id ON category_groups(parent_id);
```

---

## A3 — Centros de custo

### Novo modelo `CostCenter`

```python
class CostCenter(Base):
    __tablename__ = "cost_centers"

    id:           UUID PK
    workspace_id: UUID FK → workspaces CASCADE
    name:         str(100)      NOT NULL
    code:         Optional[str(20)]           # "MKT", "OPS", "ADM"
    description:  Optional[str(500)]
    is_active:    bool  DEFAULT True
```

### FKs adicionadas (nullable, SET NULL)

```sql
-- 104_cost_centers.py
CREATE TABLE cost_centers (...);

ALTER TABLE transactions  ADD COLUMN cost_center_id UUID REFERENCES cost_centers(id) ON DELETE SET NULL;
ALTER TABLE budgets       ADD COLUMN cost_center_id UUID REFERENCES cost_centers(id) ON DELETE SET NULL;
```

### Novo service `cost_center_service.py`

- `list_cost_centers(workspace_id, include_inactive=False)`
- `create_cost_center(workspace_id, name, code?, description?)`
- `update_cost_center(id, ...)`
- `deactivate_cost_center(id)` — sempre deactivate (nunca hard-delete se em uso); hard-delete se sem uso
- Valida: `cost_center_id` pertence ao workspace (`404` se não)

### Novas rotas `/api/cost-centers`

| Método | Rota | Permissão |
|--------|------|-----------|
| GET | `/api/cost-centers` | `read` (qualquer membro) |
| POST | `/api/cost-centers` | `admin` |
| PATCH | `/api/cost-centers/{id}` | `admin` |
| DELETE | `/api/cost-centers/{id}` | `admin` |

### Rotas existentes afetadas

- `POST /api/transactions`, `PATCH /api/transactions/{id}` → aceitam `cost_center_id?`
- `GET /api/reports/dre?cost_center_id=` → filtra DRE por CC
- `GET /api/reports/dfc?cost_center_id=` → filtra DFC por CC
- `GET /api/budgets?cost_center_id=` → filtra por CC
- `POST /api/budgets` → aceita `cost_center_id?`

---

## Frontend

### A2 — Página "Categorias" (extensão, sem página nova)

- Exibição em árvore: grupos raiz expansíveis → subgrupos → categorias folha
- Formulário de grupo: campos `código` (text input, opcional) e `natureza` (select)
- Badge de natureza colorido: verde=receita, vermelho=despesa, amarelo=custo, cinza=neutro
- Formulário de subgrupo: seletor "Grupo pai" preenchido e travado

### A3 — Nova página `/settings/cost-centers`

- Tabela: Nome, Código, Status, ações (editar, desativar/reativar)
- Formulário de criação/edição inline
- Rota registrada em `App.tsx`
- Tópico de ajuda: `topics.ts` + `frontend/src/help/content/pt-BR/cost-centers.md`

### Formulário de transação (extensão)

- Campo `Centro de custo` — combo box com CCs ativos, valor padrão nulo "(nenhum)"

### Página DRE (extensão)

- Dropdown "Centro de custo" ao lado do seletor mês/ano; padrão "Todos"

### Página de orçamentos (extensão)

- Filtro por CC; criação de orçamento aceita CC opcional

### i18n — chaves novas (en / pt-BR / es obrigatório)

- `costCenter.*` — CRUD de centros de custo
- `category.natureza.*` — labels das naturezas (Receita, Despesa, Custo, Neutro)
- `category.code` — campo código
- `dre.costCenter` — label do filtro

---

## Tratamento de erros

| Situação | Resposta |
|----------|----------|
| `parent_id` aponta para subgrupo (depth=1) | `400` — máximo 1 nível de subgrupo |
| `parent_id` cria ciclo | `400` |
| Código de grupo duplicado no workspace | `409` |
| `cost_center_id` não pertence ao workspace | `404` |
| Delete de CC em uso por transações/orçamentos | Deactivate (`200` com flag `deactivated: true`) |
| Delete de CC sem uso | Hard delete `204` |

---

## Testes

### Backend

- `test_category_group_hierarchy.py` (novo)
  - Criação válida: raiz → subgrupo → categoria
  - Rejeição de depth > 1 (subgrupo de subgrupo)
  - Rejeição de ciclo
  - Herança de natureza quando subgrupo não tem natureza própria
  - `get_tree()` retorna estrutura correta

- `test_cost_center_api.py` (novo)
  - CRUD completo com autenticação e workspace isolation
  - Delete em uso → deactivate
  - Delete sem uso → hard delete
  - `cost_center_id` inválido em transação → `404`
  - Filtro de income-expenses por CC

- `test_dre_natureza.py` (novo)
  - DRE usa natureza do grupo quando disponível
  - Fallback correto quando natureza é NULL
  - Categoria com natureza `neutro` excluída do DRE

### Frontend

- `topics.test.ts` — passa automaticamente com `cost-centers.md` criado
- `npm run i18n:check -- --strict` — paridade en/pt-BR/es

---

## Migrações

| Arquivo | O que faz |
|---------|-----------|
| `103_chart_of_accounts.py` | Adiciona `parent_id`, `code`, `natureza`, `depth` em `category_groups` |
| `104_cost_centers.py` | Cria `cost_centers`; adiciona `cost_center_id` em `transactions` e `budgets` |

Próxima migração disponível: `103` (head atual: `102_transaction_client_id.py`).

> **Nota:** `transaction_splits` não recebe `cost_center_id` — essa tabela gerencia divisão de despesas entre membros de grupo, não alocação de custo. O centro de custo fica em `transactions` (o lançamento pai).
