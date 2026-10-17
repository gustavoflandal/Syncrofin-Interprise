# Plano A9 — Separação PF/PJ com Transferências Interworkspace

**Branch:** `feature/p3-separacao-pf-pj-ap-ar`
**Data:** 2026-10-05

> Após merge do PR de A5/A6, renumerar a migração 105 para 106.

---

## Visão geral

Permite que um usuário transfira valores entre um workspace `personal` (PF) e um `business` (PJ)
que ele mesmo administra, com cada ponta registrada de forma isolada no workspace correto.
A segurança de isolamento de workspace — a invariante mais crítica do sistema — é preservada:
nenhum workspace enxerga os dados internos do outro além do valor, data e categoria da própria ponta.

---

## Decisões de design

| Questão | Decisão | Motivo |
|---------|---------|--------|
| Tabela `workspace_links`? | **Não** — MVP usa autorização por membership | Usuário com `owner`/`editor` nos dois workspaces já tem confiança implícita; link formal seria burocrático para o caso PF/PJ |
| Como distinguir do transfer normal? | Coluna `is_cross_workspace_transfer BOOLEAN` na tabela `transactions` | Permite adaptar `get_transfer_pair` e `delete` sem mudar a lógica de pareamento |
| Novo endpoint ou reusar `/transfers`? | Reusar — adicionar `to_workspace_id` opcional em `TransferCreate` | Mantém a API coesa; presença de `to_workspace_id` ativa o caminho interworkspace |
| Cancelar uma ponta? | Marcar a ponta oposta como `orphaned_cross_workspace=True` | Preserva o histórico; a ponta órfã fica visível mas não pode ser editada |

---

## Tarefas

### Tarefa 1 — Migração 105 (banco)
**Arquivo:** `backend/alembic/versions/105_interworkspace_transfers.py`

Adicionar à tabela `transactions`:
- `is_cross_workspace_transfer BOOLEAN NOT NULL DEFAULT FALSE`

### Tarefa 2 — Modelo e service (backend)
**Arquivo:** `backend/app/models/transaction.py`
- Adicionar campo `is_cross_workspace_transfer: Mapped[bool]`

**Arquivo:** `backend/app/services/transaction_service.py`
- Adicionar `create_cross_workspace_transfer(session, from_ws_id, to_ws_id, user_id, data)`
  - Valida que user tem `canWrite` em ambos os workspaces
  - Valida que `from_account` pertence a `from_ws_id` e `to_account` a `to_ws_id`
  - Cria debit em `from_ws_id` com `is_cross_workspace_transfer=True`
  - Cria credit em `to_ws_id` com `is_cross_workspace_transfer=True`
  - Ambas compartilham `transfer_pair_id`
  - Registra audit event em cada workspace
- Corrigir `get_transfer_pair`: quando `is_cross_workspace_transfer=True`, buscar sem filtro de `workspace_id`
- Corrigir `delete_transaction`: idem — localizar e marcar/deletar a ponta oposta mesmo em outro workspace

### Tarefa 3 — Schemas e API
**Arquivo:** `backend/app/schemas/transaction.py`
- `TransferCreate`: adicionar `to_workspace_id: Optional[uuid.UUID] = None`
- `TransactionRead`: adicionar `is_cross_workspace_transfer: bool = False` e `cross_workspace_partner_name: Optional[str] = None`

**Arquivo:** `backend/app/api/transactions.py`
- Rota `POST /workspaces/{id}/transfers`: quando `to_workspace_id` presente, delegar para `create_cross_workspace_transfer`
- Adicionar à ALLOWLIST de `test_write_permission_coverage.py` se necessário

### Tarefa 4 — Testes backend
**Arquivo:** `backend/tests/test_transfer_api.py` (ou novo `test_cross_workspace_transfer.py`)
- Criação bem-sucedida entre workspaces do mesmo usuário
- Rejeição quando usuário não tem acesso ao workspace de destino
- Rejeição quando conta de origem/destino não pertence ao workspace declarado
- `get_transfer_pair` retorna a contraparte do outro workspace
- Deleção de uma ponta marca a outra como órfã

### Tarefa 5 — Frontend: diálogo de transferência
**Arquivo:** `frontend/src/components/transfer-dialog.tsx`
- Toggle "Transferência entre workspaces"
- Quando ativo: seletor de workspace de destino (workspaces acessíveis, excluindo o atual)
- Seletor de conta filtrado ao workspace de destino
- Envia `to_workspace_id` no payload

### Tarefa 6 — Frontend: lista de transações e diálogo de edição
**Arquivo:** `frontend/src/pages/transactions.tsx`
- Badge "↔ PF/PJ" (ou ícone `ArrowLeftRight`) em `is_cross_workspace_transfer`

**Arquivo:** `frontend/src/components/transaction-dialog.tsx`
- Exibir nome do workspace parceiro no painel de info da transferência

### Tarefa 7 — i18n, help topics, manual
- Chaves novas em `en`, `pt-BR`, `es`: `transfers.crossWorkspace`, `transfers.crossWorkspaceToggle`, `transfers.partnerWorkspace`
- Tópico de ajuda já existe (`workspace`); adicionar seção em `workspace.md` (pt-BR, en, es)
- `npm run manual:build`

### Tarefa 8 — ENTERPRISE.md e commit
- Marcar A9 como ✅
- Commit `feat(a9): cross-workspace PF/PJ transfers`
