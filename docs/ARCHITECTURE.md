# Arquitetura do SyncroFin

> Estado analisado: código herdado do Securo v0.16.0 + recursos próprios do SyncroFin (migração Alembic `092`).
> Os recursos próprios estão descritos em [FEATURES](FEATURES.md).
> Números aproximados: ~235 módulos Python no backend, ~150 arquivos de teste de backend,
> ~300 arquivos em `frontend/src`, 3 arquivos de tradução (`en`, `pt-BR`, `es`).

## 1. Visão geral

```
                       ┌──────────────────────────────┐
   Navegador ─────────▶│  frontend (React SPA)        │  Vite (dev :5173) / nginx (prod :8080)
                       │  /api/* ──proxy──────────────┼──┐
                       └──────────────────────────────┘  │
                                                         ▼
 Agentes externos ──JWT──▶ mcp-server :8765     ┌───────────────────┐
 (Claude Desktop, n8n)     (perfil "agents")    │ backend (FastAPI) │ :8000
                                  ▲             └───────┬───────────┘
                                  │ MCP/JSON-RPC        │ SQLAlchemy async (asyncpg)
                                  └─────────────────────┤
                                                        ▼
            ┌───────────────┐   tarefas    ┌───────────────────────┐
            │ celery-worker │◀────────────▶│ Redis (broker, rate   │
            │ celery-beat   │              │ limit, cache, estado) │
            └──────┬────────┘              └───────────────────────┘
                   │                       ┌───────────────────────┐
                   └──────────────────────▶│ PostgreSQL + pgvector │
                                           └───────────────────────┘
```

Seis serviços no Compose de desenvolvimento: `db`, `redis`, `backend`, `frontend`,
`celery-worker`, `celery-beat` (+ `mcp-server` sob o perfil `agents`). O `backend`, o worker,
o beat e o MCP server usam **a mesma imagem/código** (`./backend`), mudando só o comando.
O `backend` executa `alembic upgrade head` ao subir.

Volumes: `pgdata` (banco), `attachments` (anexos), `agent_knowledge` (arquivos da base de
conhecimento), `agent_embedding_models` (modelo ONNX de embeddings, ~120 MB no primeiro uso).

## 2. Backend (`backend/`)

Camadas, de fora para dentro: **`api/` (rotas) → `services/` (regras de negócio) → `models/`
(SQLAlchemy)**, com `schemas/` (Pydantic) na fronteira HTTP e `providers/` isolando integrações
externas.

| Diretório | Papel |
|-----------|-------|
| `app/main.py` | Cria o app FastAPI, registra ~40 routers, CORS, `lifespan` (dispara sync bancário e aquece o cache do Tesouro Direto). Monta as rotas de agentes apenas se `AGENTS_ENABLED=true`. |
| `app/worker.py` | App Celery e **agenda do beat** (sync bancário, recorrências, crescimento de ativos, cotações, câmbio). |
| `app/core/` | Config (`pydantic-settings`), banco, auth (fastapi-users + JWT), contexto de workspace, rate limit (Redis), WebAuthn, feature flags, gate de módulos. |
| `app/api/` | Um arquivo por recurso (`/api/transactions`, `/api/accounts`, …). Sem regra de negócio pesada. |
| `app/services/` | Onde a lógica vive. Os maiores: `transaction_service` (77 KB), `connection_service` (108 KB, sync bancário), `dashboard_service`, `report_service`, `rule_service`, `account_service`, `asset_service`. |
| `app/models/` | ~35 entidades (ver §4). |
| `app/services/` (próprios) | `accountant_export_service`, `health_service`, `email_service`, `email_templates`, `notification_service`, `notification_delivery`, `reconciliation_auto_service`, `reconciliation_settle_service`. |
| `app/providers/` | Integrações: `pluggy`, `enable_banking`, `simplefin` (bancos), `market_price` (Yahoo/yfinance), `tesouro_direto`, `openexchangerates`, `storage`/`local_storage`. |
| `app/fiscal/` | "Jurisdiction packs" (`jurisdictions/*.toml`, ~45 países): nomes e validação de documentos fiscais (CPF/CNPJ etc.). `br.toml` é o pacote brasileiro. |
| `app/tasks/` | Tarefas Celery: `sync_tasks`, `recurring_tasks`, `asset_tasks`, `fx_rate_tasks`, `fx_backfill_tasks`, `notification_tasks`, `reconciliation_tasks`. |
| `app/agents/` | Módulo **opcional** de IA (ver §6). Autocontido. |
| `mcp_server/` | Servidor MCP embutido (app FastAPI separado, porta 8765) com ferramentas de leitura e "propostas" de escrita. |
| `alembic/versions/` | 92 migrações lineares (`001`…`092`; `091` notificações, `092` limiar de conciliação automática). `scripts/check_migration_chain.py` garante uma única cabeça. |
| `tests/` | ~150 arquivos, contra **PostgreSQL real com pgvector** (um banco por worker do xdist); inclui teste das migrações num banco novo. |

### 2.1 Multi-tenancy: usuários → workspaces

O eixo de isolamento de dados é o **workspace**, não o usuário.

- `Workspace` (`kind`: `personal` | `business`, moeda padrão, locale, jurisdição fiscal).
- `WorkspaceMember` com papéis `owner` / `editor` / `viewer`; existe também o papel virtual
  `manager` (via `managed_by_user_id`) para quem administra o workspace de outra pessoa.
- Cada request resolve o workspace por `X-Workspace-Id` (ou o padrão do usuário) em
  `core/workspace_context.py`, que devolve um `WorkspaceContext` com `role`, `can_write`,
  `is_owner`. Rotas que escrevem chamam `ctx.require_write()`.
- **Legado a conhecer:** `core/workspace_autostamp.py` preenche `workspace_id` a partir de
  `user_id` num listener `before_insert`. Existe por compatibilidade histórica; ver
  [ROADMAP](ROADMAP.md).
- Quais **módulos** (telas) cada workspace mostra é decidido por `services/module_service.py`
  (catálogo → política por `kind` → override → veto por flag de deployment). `invoices` só vem
  ligado em workspaces `business`. Isto **não** é controle de permissão.

### 2.2 Autenticação e segurança

- fastapi-users, JWT em header Bearer, expiração de 24 h. Login customizado (`custom_auth`)
  com 2FA TOTP (`two_factor`), passkeys (`passkeys`, `core/webauthn.py`) e OIDC (`oidc_auth`).
- `LOCAL_AUTH_ENABLED=false` força SSO-only (regras detalhadas em [CONFIGURATION](CONFIGURATION.md)).
- Rate limit por IP em login/registro/reset (`core/rate_limit.py`, Redis). Atrás de proxy,
  configure `TRUSTED_PROXY_HOPS`.
- Segredos de conexões LLM são cifrados em repouso (`agents/services/crypto.py`).
- Backup ZIP protegido por senha (AES-256, `pyzipper`).
- **E-mail transacional** (`services/email_service.py`, SMTP): recuperação de senha (`UserManager.on_after_forgot_password`, enviado em background para não revelar por tempo se o endereço existe) e convites de workspace (link de uso único para definir a senha). O host dos links vem de `FRONTEND_URL`, nunca do cabeçalho `Host`.
- Primeiro acesso: `GET /api/setup/status` → `POST /api/setup/create-admin` (só funciona
  enquanto não há usuários).

### 2.3 Jobs em background (Celery beat)

| Tarefa | Frequência | Nota |
|--------|-----------|------|
| `sync_all_connections` | 1 h | Pula conexões sincronizadas há < 4 h; também disparada no startup |
| `generate_all_recurring` | 1 h | Idempotente (avança `next_occurrence`) |
| `apply_asset_growth_rules` | 1 h | Idempotente |
| `refresh_market_prices` | 24 h | Um `AssetValue` por ativo por dia |
| `sync_fx_rates` | 12 h | ~60 chamadas/mês à API de câmbio |
| `restamp_recurring_fx`, `restamp_fallback_fx` | 12 h | Corrigem transações estampadas com câmbio 1:1 de fallback |
| `generate_notifications` | 1 h | Idempotente (chave por situação); envia e-mail/webhook se configurados |
| `auto_apply_suggestions` | 1 h | Só age em workspaces com limiar de conciliação definido |

### 2.4 Integrações bancárias

`providers/base.py` define o contrato `BankProvider` (`AccountData`, `TransactionData`,
`HoldingData`, resultado de refresh `refreshed|skipped|needs_user_action|failed`). Cada provider
tem um fluxo de conexão diferente (`flow_type`): **widget** (Pluggy), **oauth** (Enable Banking),
**token** (SimpleFIN). Novos providers se registram com `register_provider` e entram em
`KNOWN_PROVIDERS` em `providers/__init__.py`. A orquestração (deduplicação, pareamento de
transferências, faturas de cartão, holdings) está em `services/connection_service.py`.

## 3. Frontend (`frontend/`)

SPA React 19 + TypeScript, Vite 8, Tailwind 4, componentes shadcn/ui (`components/ui/`),
TanStack Query para dados de servidor, react-hook-form + zod para formulários, recharts / d3-sankey
para gráficos, i18next para traduções.

| Caminho | Papel |
|---------|-------|
| `src/App.tsx` | Roteamento (lazy por página). Rotas protegidas dentro de `AppLayout`; `/i/:token` (fatura pública) fica fora de auth. |
| `src/pages/` | Uma página por rota (dashboard, transactions, accounts, assets, reports, invoices, rules, groups, agents…). Várias passam de 60–125 KB (`assets.tsx`, `transactions.tsx`, `account-detail.tsx`, `dashboard.tsx`). |
| `src/components/` | Componentes de domínio (diálogos de transação, filtros, conciliação, faturas, chat de IA). |
| `src/contexts/` | `auth`, `workspace`, `collection-filter` (providers + hooks). |
| `src/lib/api.ts` | **Cliente HTTP único** (axios, ~72 KB) — todas as chamadas à API. Tipos em `src/types/index.ts`. |
| `src/lib/nav-items.ts`, `modules.ts` | Menu lateral. `modules.ts` espelha o `ModuleId` do backend; quem decide é o servidor (`workspace.enabled_modules`). |
| `src/components/` (próprios) | `notification-bell`, `financial-health-card`, `accountant-export-dialog`; `public/sw.js` + `manifest.webmanifest` (PWA). |
| `src/locales/*.json` | 3 idiomas (`en`, `pt-BR`, `es`). `en` e `pt-BR` embutidos no bundle; os demais carregam sob demanda. |
| `build/version.ts` | Resolve a versão exibida (tag git, SHA) e consulta releases do repositório para o aviso de atualização. |

Convenções úteis: alias `@/` = `src/`; testes com Vitest + Testing Library ao lado do código
(`*.test.ts(x)`); `assetsDir: 'static'` no Vite para não colidir com a rota SPA `/assets`;
o typecheck usa o compilador TypeScript nativo (`@typescript/native`).

Em produção o nginx (`default.conf.template`) serve o build e faz proxy de `/api/` para o backend
com resolução DNS em tempo de request.

## 4. Modelo de dados (principais entidades)

- **Identidade:** `User`, `UserPasskey`, `Workspace`, `WorkspaceMember`, `WorkspaceTaxId`, `AppSetting`.
- **Contas:** `Institution`, `BankConnection`, `Account` (corrente, poupança, cartão, carteira…),
  `CreditCardBill`, `Collection` (agrupamento de contas/grupos de ativos).
- **Movimentação:** `Transaction` (valor `Numeric(15,2)`, `type` debit/credit, `effective_date`
  para regime de caixa de cartões, parcelamento, anexos), `TransactionSplit`, `Category`,
  `CategoryGroup`, `Payee` (+ mapeamentos e IDs fiscais), `Rule`, `RecurringTransaction`,
  `Budget`, `Goal`, `ImportLog`, `FxRate`.
- **Conciliação:** `ReconciliationRule`, `ReconciliationSuggestion`, `ReconciliationEvent`.
- **Patrimônio:** `Asset`, `AssetGroup`, `AssetValue`, `AssetTransaction` (livro de operações; o
  preço médio é derivado — ver `docs/rfc-235-investment-ledger.md`).
- **Divisão de despesas:** `Group`, `GroupMember`, `GroupSettlement`.
- **Faturas:** `Invoice`, `InvoiceLine`, `InvoiceAllocation`, `InvoiceSettings`, `InvoiceAttachment`.
- **Agentes** (`app/agents/models/`): agente, conexão LLM, conversa/mensagens, chunks de
  conhecimento (coluna `Vector` do pgvector) e uso de tokens.

Convenções: PKs UUID; toda entidade financeira carrega `workspace_id` (FK com `CASCADE`) e
geralmente `user_id`; valores monetários em `Decimal`; moedas ISO de 3 letras; convenção do
projeto: `type='debit'` = despesa, `type='credit'` = receita.

## 5. Fluxos principais

**Importação de arquivo:** `POST /api/transactions/import` → `import_service` (parsers OFX/QIF/
CAMT/CSV + mapeamento de colunas) → deduplicação → aplicação de regras (`rule_engine`) →
detecção de transferências e de recorrências (`recurring_match_service`) → `ImportLog`.

**Sincronização bancária:** beat/startup → `sync_all_connections` → `connection_service`
→ provider → contas, transações, faturas e holdings → regras + reconciliação.

**Conciliação:** `reconciliation_engine` compara transações com regras/sugestões;
`reconciliation_portability` exporta/importa políticas (o identificador de formato ainda é `securo-reconciliation-rules`,
mantido por compatibilidade — ver "Identificadores herdados" abaixo).

**Câmbio:** transações em moeda diferente da do workspace são estampadas com taxa do dia
(`fx_rate_service`); sem chave da Open Exchange Rates usa fallback 1:1 com aviso na UI.

## 6. Módulo de agentes de IA (opcional)

Ativado por `AGENTS_ENABLED=true` (+ `COMPOSE_PROFILES=agents` no Compose). Desligado = nenhuma
rota, import ou tarefa carregada.

- **Providers de LLM** (`agents/providers/`): OpenAI, Anthropic, Ollama, OpenAI-compatível, com
  streaming (SSE). Conexões e chaves por usuário/workspace, cifradas.
- **Runtime** (`agents/runtime/executor.py`): monta o *system prompt* (identidade + contexto do
  usuário), roda o laço de tool-calling e emite gráficos via bloco de código `securo-chart`.
- **MCP:** o cliente (`agents/mcp/client.py`) conversa com o servidor embutido
  (`mcp_server/`) e com servidores extras (`AGENTS_EXTRA_MCP_SERVERS`). As ferramentas de
  escrita **nunca gravam no banco**: devolvem uma *proposta* que a UI mostra num card
  "Aplicar"; só então o endpoint normal da API é chamado. Tokens JWT (`AGENTS_MCP_JWT_SECRET`)
  autenticam clientes externos (Claude Desktop, n8n…), com TTL de 90 dias por padrão.
- **RAG:** upload de arquivos → `chunking` → `embedding` (fastembed local por padrão, modelo
  multilíngue) → busca vetorial no pgvector por agente.

## 7. Infraestrutura

- `docker-compose.yml` (dev, hot reload, build local) e `docker-compose.prod.yml` (imagens
  publicadas — **ainda inexistentes** para o novo nome).
- `charts/syncrofin/` — Helm chart completo (frontend, backend, worker, beat, mcp-server,
  PostgreSQL e Redis opcionais, Ingress ou Gateway API, PVCs). Requer storage RWX se os pods
  rodarem em nós diferentes (anexos e conhecimento são compartilhados).
- `install.sh` — instalador para Linux/macOS (gera `.env`, faz `pull` e `up`).
- `renovate.json` — atualizações automáticas de dependências; `.pre-commit-config.yaml` — ruff,
  cadeia de migrações e `ty`.
- **CI/CD:** `.github/workflows/ci.yml` (PR/push) e `release.yml` (tag `v*`: imagens multi-arch no ghcr.io, chart Helm OCI e release). Ver [DEPLOYMENT](DEPLOYMENT.md).

## 8. Identificadores herdados `securo-*` (não renomear)

O produto foi renomeado de Securo para SyncroFin, mas alguns identificadores estão **gravados em dados ou
trocados como formato de arquivo/protocolo**. Renomeá-los quebraria dados existentes ou a interoperabilidade,
então continuam com o prefixo `securo`:

| Identificador | Onde | Por quê |
|---------------|------|---------|
| `securo-agents-llm-keys-v1` | `agents/services/crypto.py` | *Salt* da chave que cifra as chaves de LLM no banco — mudar o salt torna todas ilegíveis |
| `_securo_provider_sell_date` | `services/connection_service.py` | Chave de metadado gravada nas transações de ativos |
| `securo` (servidor MCP) e prefixo `securo__<tool>` | `agents/mcp/client.py` | Salvo nas preferências de ferramentas por agente e nas mensagens de conversas |
| `_securo` (extras das tools MCP) | `mcp_server/registry.py`, `agents/mcp/client.py` | Campo de protocolo entre servidor e cliente |
| `securo-backend` / `securo-mcp` | JWT `iss`/`aud` (`agents/mcp/auth.py`, `mcp_server/auth.py`) | Tokens MCP já emitidos (TTL de 90 dias) deixariam de valer |
| `securo-chart` | bloco de código dos gráficos dos agentes | Mensagens antigas guardadas com essa tag deixariam de renderizar |
| `securo-categorization-rules`, `securo-reconciliation-rules` | campo `format` dos JSONs de regras | Arquivos exportados antes precisam continuar importáveis |

Para migrá-los um dia: faça uma migração de dados **e** aceite os dois valores na leitura por um período.
