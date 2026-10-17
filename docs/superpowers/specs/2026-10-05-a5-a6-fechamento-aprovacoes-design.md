# A5 + A6 — Fechamento de período e fluxo de aprovação: design

**Data:** 2026-10-05
**Branch:** `feature/p2-fechamento-periodo-aprovacoes`
**Itens do roadmap:** A5 (P2/M) e A6 (P2/L) de `docs/ENTERPRISE.md`

## Objetivo

Adicionar dois controles de governança financeira ao SyncroFin Enterprise:

- **A5 — Fechamento de período:** impedir criação, edição e exclusão de transações em meses
  encerrados pelo financeiro, com histórico auditado de quem fechou/reabriu e por quê.
- **A6 — Fluxo de aprovação:** reter transações que superam um threshold configurado no workspace
  em fila de pendentes até que um aprovador autorizado as aprove; segregar funções (criador ≠
  aprovador).

Ambos são guards na camada de serviço, configuráveis por workspace e integrados ao RBAC existente
(C2). Nenhum altera o modelo de partidas nem o DRE/DFC além de filtros de exclusão.

---

## 1. Modelo de dados

### Migração `103_period_close_approval`

#### Nova tabela `period_closes`

| Coluna | Tipo | Notas |
|--------|------|-------|
| `id` | uuid PK | |
| `workspace_id` | uuid FK workspaces CASCADE | |
| `year` | int NOT NULL | |
| `month` | int NOT NULL | 1..12 |
| `closed_by_user_id` | uuid FK users SET NULL | nullable após exclusão do user |
| `closed_at` | timestamptz NOT NULL | |
| `reason` | text | nullable |
| `reopened_by_user_id` | uuid FK users SET NULL | nullable; null = ainda fechado |
| `reopened_at` | timestamptz | nullable |
| `reopen_reason` | text | nullable |

**Constraint:** `UNIQUE (workspace_id, year, month)` — apenas uma entrada por período/workspace.
Um período está fechado quando `reopened_at IS NULL`.

#### Nova tabela `workspace_approval_rules`

| Coluna | Tipo | Notas |
|--------|------|-------|
| `id` | uuid PK | |
| `workspace_id` | uuid FK workspaces CASCADE | |
| `category_group_id` | uuid FK category_groups SET NULL | nullable = regra global |
| `amount_threshold` | numeric(20,4) NOT NULL | valor absoluto (positivo) |
| `currency` | varchar(3) NOT NULL default 'BRL' | |
| `created_by_user_id` | uuid FK users SET NULL | |

**Constraint:** `UNIQUE (workspace_id, category_group_id)` — um threshold por grupo (null = global).
O threshold de um grupo específico substitui o global; o global é o fallback.

#### Nova tabela `approval_events`

| Coluna | Tipo | Notas |
|--------|------|-------|
| `id` | uuid PK | |
| `transaction_id` | uuid FK transactions CASCADE | |
| `actor_user_id` | uuid FK users SET NULL | |
| `action` | varchar(20) NOT NULL | `submitted` \| `approved` \| `rejected` \| `cancelled` |
| `note` | text | nullable |
| `occurred_at` | timestamptz NOT NULL | |

#### Colunas novas em tabelas existentes

**`transactions`**
- `approval_status varchar(20) nullable` — `null` = não requer aprovação, `'pending'` = aguardando,
  `'approved'` = aprovado, `'rejected'` = rejeitado.

**`workspaces`**
- `period_close_by varchar(20) NOT NULL default 'date'` — `'date'` | `'effective_date'`. Determina
  qual data da transação é verificada contra os períodos fechados.
- `period_close_sync_mode varchar(20) NOT NULL default 'reject'` — `'reject'` | `'pending_review'`
  | `'allow'`. Controla o comportamento de sync bancário e importações quando o período está fechado.

---

## 2. Permissões RBAC

Dois novos itens no catálogo `backend/app/core/permissions.py`:

```python
Permission("periods.manage", "admin"),   # fechar e reabrir períodos
Permission("approvals.approve", "data"), # aprovar ou rejeitar transações pendentes
```

Herança pelos roles de sistema:
- `owner` e `manager`: recebem ambas (herdam `ALL_PERMISSIONS`).
- `editor`: **não** recebe nenhuma das duas.
- `viewer`: idem.
- Roles customizadas: o owner pode atribuir qualquer uma a membros específicos.

---

## 3. Camada de serviço

### `services/period_close_service.py` (novo)

```python
async def is_period_closed(session, workspace, date: date) -> bool
    # Verifica se (year, month) da `date` (ou effective_date conforme workspace.period_close_by)
    # tem entrada em period_closes com reopened_at IS NULL.

async def close_period(session, workspace_id, user_id, year, month, reason) -> PeriodClose
    # Cria entrada; levanta HTTPException 409 se já estiver fechado.

async def reopen_period(session, workspace_id, user_id, year, month, reason) -> PeriodClose
    # Preenche reopened_at/reopened_by; levanta 404 se não existir ou 409 se já aberto.

async def list_period_closes(session, workspace_id) -> list[PeriodClose]
    # Retorna todos os registros ordenados por (year DESC, month DESC).
```

**Guard `_assert_period_open`** — helper privado chamado no início de
`create_transaction`, `update_transaction` e `delete_transaction` em
`transaction_service.py`. Levanta `HTTPException 422` com
`{"code": "period_closed", "period": "YYYY-MM"}` se o período estiver fechado.

**Guard em `import_service` e `connection_service`** — antes de inserir cada transação,
verifica `is_period_closed`. Comportamento conforme `workspace.period_close_sync_mode`:
- `reject`: transação ignorada; linha de log com `import_log` ou `connection_log`.
- `pending_review`: insere com `transaction.status = 'pending_review'`.
- `allow`: bypass da verificação.

### `services/approval_service.py` (novo)

```python
async def get_threshold(session, workspace_id, transaction) -> Decimal | None
    # Resolve o threshold: primeiro busca regra para o category_group do lançamento,
    # fallback para regra global (category_group_id IS NULL). Retorna None se não há regra.

async def needs_approval(session, workspace_id, transaction) -> bool
    # True se abs(transaction.amount) > threshold e threshold não é None.

async def submit_for_approval(session, transaction, actor_user_id) -> None
    # Define approval_status = 'pending'; insere ApprovalEvent(action='submitted').

async def approve(session, transaction_id, workspace_id, actor_user_id, note) -> Transaction
    # Valida permissão approvals.approve.
    # Impede que o criador aprove a própria transação (segregação C3).
    # Define approval_status = 'approved'; insere ApprovalEvent(action='approved').

async def reject(session, transaction_id, workspace_id, actor_user_id, note) -> Transaction
    # Valida permissão approvals.approve.
    # Define approval_status = 'rejected'; insere ApprovalEvent(action='rejected').

async def cancel(session, transaction_id, workspace_id, actor_user_id) -> Transaction
    # Só o criador original (transaction.user_id) pode cancelar.
    # Define approval_status = 'rejected'; insere ApprovalEvent(action='cancelled').
    # Não exclui a transação — o criador pode excluí-la em seguida se quiser.

async def list_pending(session, workspace_id) -> list[Transaction]
    # WHERE approval_status = 'pending' ORDER BY date DESC.
```

**Integração em `create_transaction`**: após persistir a transação, chama `needs_approval`. Se
`True`, chama `submit_for_approval` antes de retornar.

**Filtro nos relatórios**: `report_service.py`, `dashboard_service.py` e a query padrão de
`list_transactions` adicionam `WHERE approval_status IS NULL OR approval_status = 'approved'`.
A tela de aprovações usa `include_pending=True` para ver as pendentes.

---

## 4. API

### `api/period_closes.py` (novo router, prefixo `/period-closes`)

| Método | Rota | Permissão | Descrição |
|--------|------|-----------|-----------|
| `POST` | `/` | `periods.manage` | Fechar período `{year, month, reason?}` |
| `DELETE` | `/{year}/{month}` | `periods.manage` | Reabrir período `{reason}` |
| `GET` | `/` | membro | Listar períodos fechados |

### `api/approvals.py` (novo router, prefixo `/approvals`)

| Método | Rota | Permissão | Descrição |
|--------|------|-----------|-----------|
| `GET` | `/pending` | `approvals.approve` | Fila de pendentes |
| `POST` | `/{tx_id}/approve` | `approvals.approve` | Aprovar `{note?}` |
| `POST` | `/{tx_id}/reject` | `approvals.approve` | Rejeitar `{note?}` |
| `POST` | `/{tx_id}/cancel` | `transactions.write` | Cancelar (só criador) |
| `GET` | `/threshold` | membro | Verificar threshold para um valor/categoria |

`GET /transactions` e `GET /transactions/{id}` passam a expor `approval_status` no response.
O payload `TransactionCreate` não muda.

Ambos os routers são registrados em `app/main.py` com tag `workspace` e aplicam
`WorkspaceContext` normalmente.

---

## 5. Frontend

### Tela "Períodos" (`/periods`)

- Tabela de meses com ícone cadeado (fechado/aberto), nome do responsável e data.
- Botão **Fechar período**: modal com campo de razão.
- Botão **Reabrir**: confirmação com campo de razão obrigatório.
- Acesso condicionado à permissão `periods.manage`; membros sem permissão veem a lista
  em modo leitura.
- Rota e tópico de ajuda: `periods` (adicionado em `topics.ts`).

### Tela "Aprovações" (`/approvals`)

- Fila de transações com `approval_status = 'pending'`: valor, categoria, conta, quem enviou, data.
- Botões **Aprovar** / **Rejeitar** com campo de nota.
- Badge numérico no nav lateral quando há pendentes.
- Acesso condicionado a `approvals.approve`; o criador vê suas próprias pendentes (filtro
  separado no mesmo endpoint com `created_by_me=true`).
- Rota e tópico de ajuda: `approvals`.

### Integrações nas telas existentes

- **`TransactionForm`**: aviso inline "Esta transação precisará de aprovação" quando o valor
  supera o threshold do workspace (busca via `GET /approvals/threshold?amount=X&category_group_id=Y`).
- **`TransactionList`**: badge `Pendente` / `Rejeitado` na linha; transações rejeitadas em
  cinza com opção de cancelar.
- **`Settings/Workspace` — aba "Fechamento & Aprovações"**: campos `period_close_by` e
  `period_close_sync_mode`; tabela CRUD de `workspace_approval_rules`.

### i18n

Chaves novas em `en`, `pt-BR` e `es` nos namespaces:
- `periods.*`: `title`, `close`, `reopen`, `reason`, `closedBy`, `closedAt`, `noClosedPeriods`, erro `period_closed`
- `approvals.*`: `title`, `pending`, `approve`, `reject`, `cancel`, `note`, `approvedBy`, `needsApproval`, `noPending`

---

## 6. Testes

### Backend

- `test_period_close_service.py`: fechar, reabrir, tentar fechar já fechado (409), verificar bloqueio em create/update/delete, sync com cada modo.
- `test_approval_service.py`: threshold global, threshold por grupo, fallback global, criador não pode aprovar, aprovação/rejeição/cancelamento, filtro em list_transactions e report_service.
- `test_period_close_api.py` e `test_approval_api.py`: cobertura de permissões (editor rejeitado em periods.manage e approvals.approve).
- `test_write_permission_coverage.py`: rotas novas declaradas com permissão (não entram na ALLOWLIST).

### Frontend

- `periods.test.tsx`: renderiza lista, abre/fecha modal, feedback de erro de período fechado.
- `approvals.test.tsx`: renderiza fila, aprova, rejeita, badge numérico.
- `topics.test.ts`: verifica que `periods` e `approvals` têm arquivo `pt-BR/*.md`.
- `i18n:check --strict`: 0 chaves faltando.

---

## 7. Critérios de aceite

1. Criar transação em período fechado retorna 422 com `code: "period_closed"`.
2. Sync bancário com período fechado segue `period_close_sync_mode` do workspace.
3. Transação acima do threshold é criada com `approval_status = 'pending'` e **não aparece** no DRE/DFC/saldo.
4. Criador não pode aprovar a própria transação.
5. Transação aprovada entra nos cálculos normalmente.
6. `periods.manage` e `approvals.approve` não são concedidas a `editor` ou `viewer`.
7. Reabertura de período é registrada na tabela `period_closes` com `reopened_by_user_id`.
