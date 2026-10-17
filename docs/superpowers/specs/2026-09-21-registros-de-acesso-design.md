# Registros de acesso (D3) — desenho

Data: 2026-09-21 · Item: D3 do [ENTERPRISE](../../ENTERPRISE.md) · Contexto: [FASE1](../../FASE1.md) (D1/D3)
Branch: `feat/registros-de-acesso` · Sucessor: D1 (canal do titular), num PR próprio.

## 1. Objetivo

Dar ao administrador da instância um **registro de acessos** consultável e exportável, dar a cada pessoa o **histórico
dos próprios acessos**, e tratar a **guarda** desses registros: mínimo de 6 meses (Marco Civil, art. 15), **prazo configurável
em Administração** e **anonimização automática** depois do prazo (LGPD: não guardar dado pessoal além do necessário).

Não cria uma tabela nova: os eventos de acesso já vivem em `audit_events` (append-only, com cadeia de hashes). O D3 acrescenta
um conjunto nomeado de ações, um evento que faltava (uso de token de API), consultas próprias, telas, o parâmetro de guarda e o
descarte por anonimização.

## 2. O que já existe

- `audit_events`: trigger que recusa `UPDATE`/`DELETE`/`TRUNCATE` (a única exceção é a função de selagem), cadeia de hashes
  (`hash = sha256(prev_hash || conteúdo)`), `ip`, `user_agent`, `actor_user_id`, `actor_kind`, `detail`. Sem chaves estrangeiras
  (a trilha sobrevive à pessoa apagada). `verify` lê buraco na sequência como adulteração.
- Eventos gravados hoje: `login` (com o método em `detail`), `login_failed` (`bad_password`, `bad_2fa_code`, `inactive`,
  `unknown_user`), `login_blocked`, `account_locked`, `account_unlocked`, `session_revoked` (motivo em `detail`; sair é `logout`).
- `GET /api/audit/instance` (administrador, sem tela) e `/api/audit` (dono do workspace). Os eventos de acesso têm
  `workspace_id` nulo, por isso a tela de auditoria do workspace nunca os mostra.
- Token de API: só atualiza `last_used_at`, no máximo 1×/min (`api_token_service`), sem rastro na trilha.
- Tarefa Celery `seal_audit_events` (a cada minuto, `worker.py`/`tasks/audit_tasks.py`); `app_settings` guarda parâmetros da
  instância (ex.: `mfa_grace_days`), editados em Administração.

## 3. Dados e regras

### 3.1 Conjunto de acesso

Novo módulo `core/access_log.py`, fonte única para consultas, índice, trigger e testes:

- `ACCESS_ACTIONS = ("login", "login_failed", "login_blocked", "account_locked", "account_unlocked", "session_revoked", "token_access")`.
- `ACCESS_MIN_RETENTION_DAYS = 183`, `ACCESS_MAX_RETENTION_DAYS = 3650`.
- `REDACTED_COLUMNS = ("actor_user_id", "entity_id", "changes", "ip", "user_agent", "request_id", "detail")`.
- Rótulo legível por ação/motivo fica no frontend (chaves i18n); o servidor devolve só códigos.

### 3.2 Novo evento `token_access`

- Gravado quando um token de API **autentica com sucesso**, no máximo **1 por par (token, IP) por hora**.
- Controle por chave no Redis `token_access:{token_id}:{ip}` com TTL de 1 h (`SET NX EX 3600`). O primeiro uso e qualquer IP
  novo geram evento na hora.
- Campos: `actor_kind = api_token`, `actor_user_id` = dono do token, `workspace_id` = workspace do token, `entity_type =
  api_token`, `entity_id` = id do token, `detail = api_token:<prefixo>` (mesmo formato que a auditoria de escritas já usa), `ip` e
  `user_agent` do contexto da requisição.
- **Falha do Redis:** grava o evento mesmo assim (o registro falha aberto; a requisição nunca falha por causa dele).
- **Token inválido, expirado ou revogado não gera evento**: uma trilha que nunca encolhe não pode ser enchida por quem
  não tem credencial nenhuma.

### 3.3 Prazo de guarda (parâmetro do sistema)

- Chave `access_log_retention_days` em `app_settings`. Sem valor gravado, vale `ACCESS_LOG_RETENTION_DAYS` do ambiente
  (padrão **183**).
- Aceita **183 a 3650** dias. O servidor recusa fora disso (422); o banco também impõe o piso (3.4).
- `GET /api/admin/access-log/retention` → `{days, minimum, maximum}`; `PUT` com `{days}` (administrador). Alterar entra na trilha
  sozinho: `app_settings` já é auditada (evento `update` com o valor antes e depois).
- **Cartão "Prazo de guarda dos registros de acesso"** na página de Administração, ao lado do cartão de 2FA.

### 3.4 Descarte por anonimização

Apagar de verdade uma linha no meio da cadeia global de hashes deixaria um buraco que o `verify` lê como adulteração. Por isso
o descarte **anonimiza**: a linha continua, os dados pessoais somem.

- Ao vencer o prazo, as colunas de `REDACTED_COLUMNS` viram `NULL` e `purged_at` recebe a data. Ficam `id`, `seq`, `occurred_at`,
  `actor_kind`, `workspace_id`, `action`, `entity_type`, `prev_hash` e `hash`.
- **Trigger** (função `audit_events_immutable`, migração `099`): ganha uma segunda exceção, além da selagem. Um `UPDATE` só passa se
  `audit.purging = 'on'` (definido pela função de descarte) **e** a linha é de ação de acesso, já selada (`hash` não nulo), ainda
  não anonimizada, com **mais de 183 dias**, e **só** as colunas de `REDACTED_COLUMNS` e `purged_at` mudam (as redigidas ficam
  nulas e `purged_at` fica preenchido). Qualquer outra alteração continua recusada. O piso de 6 meses vale no banco: nem um
  erro no código anonimiza um evento recente.
- **Função SQL** `audit_events_purge_access(retention_days integer, batch integer) RETURNS integer`: usa
  `GREATEST(retention_days, 183)`, anonimiza até `batch` linhas seladas e vencidas (mais antigas primeiro) e devolve quantas.
- **Tarefa Celery** `app.tasks.audit_tasks.purge_access_log`, **diária**: lê o prazo, chama a função em lotes de 10.000 até
  esgotar e, se anonimizou algo, grava o evento `access_log_purged` (ator `system`, `detail = "<n> eventos, prazo <d> dias"`).
  Esse evento **não** pertence a `ACCESS_ACTIONS` (é do sistema, não um acesso).
- **`verify`** (`VERIFY_QUERY`): para linhas anonimizadas, não recalcula o conteúdo (ele não existe mais); continua conferindo a
  sequência e o encadeamento (`prev_hash`) delas. As demais linhas seguem verificadas por inteiro.
- **Consultas e histórico próprio** ignoram linhas anonimizadas (`purged_at IS NULL`): não têm pessoa nem IP para mostrar.
- **Efeito numa instância existente:** eventos de acesso com mais de 183 dias são anonimizados na primeira execução da tarefa,
  salvo se o administrador aumentar o prazo antes. Documentado no manual e em `CONFIGURATION.md`.

### 3.5 Migração `099`

- Coluna `audit_events.purged_at timestamptz NULL`.
- Substitui `audit_events_immutable()` (cópia congelada na migração, com a lista de ações de acesso literal) e cria
  `audit_events_purge_access(...)`.
- Índice parcial `ix_audit_events_access` em `(occurred_at DESC) WHERE action IN (<acesso>) AND purged_at IS NULL`.
- Sem mudança na função de digest e, portanto, sem efeito nos hashes já gravados. As alterações também entram em
  `models/audit.py` (coluna, índice e SQL), porque o esquema dos testes vem de `create_all` + `install_audit_ddl`.
- Acrescentar uma ação ao conjunto exige nova migração (trigger, função e índice); o comentário de `access_log.py` diz isso e
  um teste compara `ACCESS_ACTIONS` com o texto da função no banco.

## 4. API

Reaproveita `_filters`, `_page`, `_csv`, `_select_with_actor` e `_read` de `api/audit.py`.

| Rota | Quem | O que faz |
|------|------|-----------|
| `GET /api/admin/access-log` | administrador da instância (`current_superuser`) | Lista paginada. Filtros: `from`, `to`, `actor_user_id`, `ip` (igualdade), `action` (só valores de `ACCESS_ACTIONS`; outro → 422), `page`, `limit` (≤ 200). |
| `GET /api/admin/access-log/export` | idem | CSV com o mesmo filtro, `seal()` antes (traz os hashes), limite de 100.000 linhas. |
| `GET /api/admin/access-log/retention` | idem | Prazo de guarda vigente e limites. |
| `PUT /api/admin/access-log/retention` | idem | Altera o prazo (183 a 3650). |
| `GET /api/auth/access-history` | a própria pessoa | Eventos de `ACCESS_ACTIONS` em que `actor_user_id` é ela (inclui `token_access` dos tokens dela). Paginado (≤ 100), sem filtros. |

- `access-history` **nunca** aceita `actor_user_id` do cliente: o filtro vem da sessão.
- Consultar o registro **não** grava evento.
- Tokens de API não acessam nenhuma delas (rotas de pessoa/instalação já respondem `403 API_TOKEN_NOT_ALLOWED`).
- `access-history` passa pelo bloqueio de 2FA por sessão (não entra em `ENROLMENT_ROUTES`).
- Cada linha: `occurred_at` (UTC), `actor_user_id`, `actor_email` (quando a conta existe), `actor_kind`, `action`, `detail`, `ip`,
  `user_agent`, `hash`. O histórico próprio omite `hash` e `actor_*`.
- A única rota nova de escrita é `PUT .../retention`: entra na allowlist de escrita como administração da instância.

## 5. Telas

- **Registros de acesso** (página de administração): tabela com filtros (período, pessoa, IP, ação), exportar CSV e o aviso
  "Guardados por {N} dias, sem possibilidade de edição; depois disso, anonimizados" (N vem do parâmetro). Pessoa apagada aparece
  como "conta removida", como na auditoria.
- **Administração → cartão de prazo de guarda:** campo de dias com o mínimo e o máximo, salvar, e o texto explicando a
  anonimização e o efeito ao reduzir/aumentar o prazo.
- **Sessões** (`sessions-dialog.tsx`): seção "Últimos acessos" com os 20 mais recentes da própria pessoa: quando, o que
  aconteceu, dispositivo (mesmo rótulo da lista de dispositivos) e IP. O motivo de falha vem em texto humano (senha errada,
  código de 2FA errado, conta bloqueada, conta desativada).
- Textos em en/pt-BR/es (`npm run i18n:check -- --strict`). Manual (`seguranca-conta.md`, `administracao.md`) atualizado e
  `docs/MANUAL.md` regenerado.

## 6. Erros e casos de borda

- Não administrador nas rotas de administração → 403. `action` fora do conjunto ou dias fora de 183–3650 → 422.
- Pessoa apagada: o evento permanece; `actor_email` nulo.
- Falha do Redis no controle de 1 h: evento gravado.
- Evento de acesso sem IP (chamada interna): coluna nula, exibida como "—".
- Evento ainda não selado nunca é anonimizado (só linhas com `hash`); com 183 dias de idade, isso é só teórico.
- Prazo reduzido de 400 para 183 dias: na próxima execução, eventos entre 183 e 400 dias são anonimizados, o que o cartão avisa
  antes de salvar.

## 7. Testes

- **Backend (Postgres real):**
  - conjunto de ações; `token_access` uma vez por hora e por IP (dois IPs → dois eventos); nada para token inválido, expirado ou
    revogado; falha do Redis não impede o evento nem a requisição; guarda de código (toda ação de `ACCESS_ACTIONS` é gravada em
    algum lugar de `app/`);
  - consultas: filtros e paginação; CSV com hashes e BOM; usuário comum → 403; pessoa A não vê acesso da pessoa B, mesmo
    passando `actor_user_id`; token → 403; linhas anonimizadas ficam de fora;
  - guarda: `DELETE` e `UPDATE` comuns continuam recusados; anonimização recusada para evento de menos de 183 dias, para ação
    fora do conjunto, para linha não selada e para qualquer outra coluna; a anonimização aceita zera exatamente
    `REDACTED_COLUMNS`; não se desfaz; `verify` continua `ok` depois; função respeita prazo maior que o piso (evento de 300 dias
    fica com prazo 400); tarefa em lotes e evento `access_log_purged`; `ACCESS_ACTIONS` bate com o texto da função e do índice
    no banco; nenhum código de `app/` emite `DELETE FROM audit_events`;
  - parâmetro: leitura, alteração dentro e fora dos limites, valor gravado fora da faixa é limitado ao ler, evento de auditoria da alteração, 403 para não administrador.
- **`test_write_permission_coverage`:** `PUT .../retention` na allowlist com o motivo "administração da instância".
- **Frontend:** vitest da página, do cartão de prazo e da seção "Últimos acessos"; `tsc`, `eslint`, `i18n:check` limpos.
- **e2e no stack real:** login, falhas, bloqueio, uso de token, conferência nas telas e no CSV, alterar o prazo e rodar a tarefa
  de descarte sobre eventos antigos criados para o teste.
- Antes do PR: suíte completa, `ruff`, `ty`, `check_migration_chain.py`.

## 8. Fora do D3

- Descarte dos **demais** eventos da trilha (mudanças de dados): segue no D2. A anonimização criada aqui pode servir de base ao D1
  (eliminação de titular), mas o uso nesse fluxo é decisão do D1.
- Alerta de IP incomum e geolocalização.
- Registro de tentativas com token inválido.
- Leitura de dados por token (só o acesso do token é registrado, não cada requisição).
- Parecer jurídico: o registro cobre o lado técnico do Marco Civil; o enquadramento da instância no art. 15 é do cliente.

## 9. Riscos

- **Mexer no trigger de imutabilidade:** é a proteção central do C1. Mitigação: a nova exceção é estreita (ação de acesso, selada,
  mais de 183 dias, colunas fixas, flag definida só pela função de descarte) e coberta por testes que tentam cada desvio.
- **Anonimização não é apagar a linha:** sobram data, ação e hashes, sem pessoa nem IP. É o preço de manter a cadeia verificável.
- **Crescimento da trilha:** `token_access` soma ~24 linhas/dia por integração ativa 24 h. A anonimização não reduz o número de
  linhas, só o conteúdo pessoal.
- **Efeito na primeira execução** em instância existente (3.4): comunicado no manual e na configuração.
- **Conjunto fixo no trigger, na função e no índice:** nova ação de acesso exige migração (comentado no código e testado).
