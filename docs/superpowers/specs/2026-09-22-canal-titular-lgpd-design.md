# Canal do titular (D1) — desenho

Data: 2026-09-22 · Item: D1 do [ENTERPRISE](../../ENTERPRISE.md) · Contexto: [FASE1](../../FASE1.md) (D1/D3)
Branch: `feat/canal-titular` (a criar) · Predecessor: D3 (registros de acesso), já mergeado (PR #20).
Fora deste PR: os documentos jurídicos (política de privacidade, RIPD, registro de operações de tratamento em
`docs/lgpd/`) — ficam para um PR de documentação à parte, por precisarem de revisão jurídica de qualquer forma.

## 1. Objetivo

Dar a cada pessoa titular de dados um canal para solicitar **acesso**, **portabilidade**, **correção** e
**eliminação** dos próprios dados (LGPD art. 18), com protocolo, prazo e registro do atendimento — a parte de
código do D1. Acesso e portabilidade são atendidos **na hora**; correção é autoatendida quando o campo já é
editável e só vira fila do administrador quando não é; eliminação é autoatendida com reautenticação e uma
checagem que impede apagar uma conta que é dona única de um workspace com outras pessoas dentro.

## 2. O que já existe

- `export.py`: `GET/POST /api/export/backup` gera um zip com todas as entidades financeiras de **um workspace**
  (JSON, opcionalmente cifrado com senha). Não inclui perfil, sessões, tokens de API nem o histórico de acesso —
  serve de base, mas precisa crescer para cobrir a pessoa, não só o workspace.
- `admin_service.delete_user`: cascade de exclusão (transações, contas, orçamentos, regras, ativos, categorias,
  conexões bancárias, o próprio usuário) — hoje só acionável pelo administrador. Bloqueia apagar o último
  superusuário. **Não** checa se a pessoa é dona única de um workspace com outros membros.
- `AuditEvent.actor_user_id`: coluna UUID **sem chave estrangeira** — a cadeia de hashes do C1 sobrevive à pessoa
  sendo apagada (a referência fica órfã, o que já é uma anonimização de fato).
- D3 (`core/access_log.py`, `access_log_service.py`): padrão de anonimização de linha em vez de apagar, evento
  próprio no C1, tela de administração e histórico próprio — modelo a seguir aqui para os eventos deste fluxo.
- **Não existe** hoje reautenticação por senha para uma pessoa já logada (a troca de senha por
  `PATCH /api/users/me` não pede a senha atual — item de backlog anotado à parte). Este PR introduz o primeiro
  uso desse padrão, só para a eliminação.
- `WorkspaceMember.role` (`owner`/`editor`/`viewer`): já existe a checagem de "dono único" para outros fins? Não —
  será nova aqui.

## 3. Dados e regras

### 3.1 Tabela `data_subject_requests`

Migração `100` (`backend/alembic/versions/100_data_subject_requests.py`):

| coluna | tipo | nota |
|---|---|---|
| `id` | UUID | PK |
| `protocol` | `varchar(20)` | único; formato `DSR-{ano}-{sequencial 6 dígitos}`, gerado em código (sequência simples por ano, sem depender de sequence do Postgres) |
| `user_id` | FK `users.id`, `ON DELETE CASCADE` | diferente de `actor_user_id` do C1: aqui é intencional que a linha suma junto com a pessoa — quem preserva a evidência de atendimento é o evento no C1 (sem FK), não este registro operacional |
| `kind` | `varchar(20)` | `access`, `portability`, `correction`, `erasure` |
| `status` | `varchar(20)` | `resolved_auto`, `pending`, `resolved_manual`, `rejected` |
| `created_at` | timestamptz | |
| `due_at` | timestamptz | `created_at + DATA_REQUEST_DEADLINE_DAYS` (env, padrão **15**) |
| `resolved_at` | timestamptz, nullable | |
| `detail` | text, nullable | texto livre da pessoa (ex.: o que quer corrigir) |
| `resolution_note` | text, nullable | preenchido pelo administrador ao resolver manualmente |

Índices: `(user_id, created_at)`, parcial `(due_at) WHERE status = 'pending'` (para a consulta de vencidas).

Cada `create`/`update` da linha já vira evento no C1 **sozinho** — não por chamada manual de `record_event` como
o D3 fez para o histórico de acesso (aquele padrão existe para eventos nomeados sem linha própria, tipo
`login`), mas pelo mecanismo genérico que já audita toda escrita ORM (`core/audit.py`, `AUDITED`): basta
acrescentar `DataSubjectRequest` à lista, e o `entity_type` sai `data_subject_requests` automaticamente. É o
caminho comum de quase todo outro modelo do sistema — o D3 foi a exceção, não a regra. Na eliminação, a própria
linha some em cascade junto com a pessoa (é dado operacional, não a evidência de conformidade em si); o que
sobra e preserva a rastreabilidade é o evento `create` já gravado em `audit_events`, que não tem FK e sobrevive
a qualquer coisa.

### 3.2 Acesso e portabilidade

Mesmo handler para os dois `kind` (a LGPD nomeia separado; o pacote é idêntico). Gera um zip maior que o
`backup` atual:

- Todo workspace onde a pessoa é membro (reaproveitando `_collect`/`build_backup_archive` de `export.py`, um
  por workspace, dentro do mesmo zip).
- Perfil (`nome`, `e-mail`, preferências, idioma), sessões (ativas e revogadas, mesmos campos da tela de
  sessões), tokens de API (metadados — nome, escopos, criado em, último uso — nunca o segredo), histórico de
  acesso próprio (mesma consulta da rota `access-history` do D3).
- `status = resolved_auto` imediatamente; a resposta já inclui o zip (como o `backup` hoje) ou um link de
  download de curta validade, a decidir na implementação conforme o tamanho típico do pacote.

### 3.3 Correção

Corpo da solicitação tem um campo `self_service: bool`. Quando `true`, a rota devolve (sem persistir nada além
do protocolo) uma lista fixa de links para onde a pessoa já pode editar sozinha (perfil, lançamentos, contas,
categorias) — `resolved_auto`. Quando `false`, exige `detail` (o que não consegue corrigir) e nasce `pending`,
visível na fila do administrador.

### 3.4 Eliminação

1. **Reautenticação:** corpo exige a senha atual; validada contra `user.hashed_password` (primeiro uso desse
   padrão no backend — função pequena e reaproveitável, não um sistema de reautenticação genérico).
2. **Checagem de dono único:** para cada workspace onde `role = owner`, se existir outro `WorkspaceMember`
   **ativo** além dela, a rota responde 409 com a lista desses workspaces e a mensagem de que é preciso
   transferir a titularidade ou remover os demais membros antes. Nada é apagado.
3. **E-mail de confirmação**, enviado **antes** de excluir (o endereço deixa de existir depois).
4. **Exclusão:** o cascade de `admin_service.delete_user` é extraído para uma função de serviço compartilhada
   (`user_deletion_service.delete_user_data`), chamada tanto pelo admin quanto por este fluxo — sem duplicar a
   lista de tabelas. Diferença: aqui não há checagem de "último superusuário" (uma pessoa comum não é
   superusuário) e a checagem de dono único do passo 2 substitui a checagem equivalente do admin.
5. `status = resolved_auto`, evento `data_request_resolved` gravado **antes** do `DELETE` do usuário (a
   solicitação em si seria apagada em cascade junto — por isso o evento no C1 é o que sobra).

## 4. API

Novo `app/api/data_requests.py`:

| Rota | Quem | O que faz |
|---|---|---|
| `POST /api/data-requests` | pessoa autenticada | Cria e, para `access`/`portability` e `correction` autoatendida, já resolve e devolve o resultado no mesmo request. |
| `GET /api/data-requests` | idem | Lista as próprias solicitações (protocolo, tipo, status, prazo). |
| `POST /api/data-requests/erasure` | idem | Rota própria (não passa pelo `POST` genérico) — corpo com senha; devolve 409 com a lista de workspaces se bloqueada. |
| `GET /api/admin/data-requests` | administrador (`current_superuser`) | Fila, filtro por `status`, destaque para `due_at` vencido. |
| `PATCH /api/admin/data-requests/{id}` | idem | Resolve (`resolved_manual`) ou rejeita (`rejected`) com `resolution_note`. Rota de escrita — entra na allowlist. |

- Tokens de API não acessam nenhuma delas (mesmo padrão do D3: pessoa, não integração).
- `access-history`, `backup` e as demais rotas reaproveitadas continuam exigindo a permissão que já exigem hoje
  (o pacote de acesso/portabilidade é montado internamente, sem repetir a checagem de permissão por workspace —
  a pessoa sempre pode ver os próprios dados).

## 5. Telas

- Nova seção **"Meus dados"** (perto de "Sessões"): botão exportar (acesso/portabilidade), formulário de
  correção, botão de eliminação de conta com o aviso de bloqueio quando aplicável, lista das solicitações
  feitas com protocolo/status/prazo.
- **Administração → "Solicitações de titulares"** (irmã de "Registros de acesso" do D3): fila de `pending`,
  vencidas em destaque, campo de resolução. Cartão de contagem em Administração.
- Textos em en/pt-BR/es; manual (`seguranca-conta.md`, `administracao.md`) atualizado e `docs/MANUAL.md`
  regenerado.

## 6. Erros e casos de borda

- Eliminação sem outros membros em nenhum workspace próprio: segue direto, sem bloqueio.
- Eliminação bloqueada e a pessoa transfere a titularidade depois: precisa abrir nova solicitação (a antiga fica
  `resolved_auto`? Não — vira `rejected` com nota automática "bloqueada por titularidade de workspace", e a
  pessoa abre uma nova depois de resolver).
- Duas solicitações de eliminação seguidas (a primeira ainda não confirmada por e-mail, se um segundo fator for
  adicionado depois): fora de escopo aqui — o e-mail é só confirmação informativa, não uma segunda etapa
  obrigatória. Se o usuário quiser um fluxo de dupla confirmação (link no e-mail antes de executar), é uma
  pergunta em aberto — o desenho atual decide executar de imediato após senha + checagem, como o app já faz para
  outras ações sensíveis.
- Correção `self_service=false` sem `detail`: 422.
- Administrador tentando `PATCH` uma solicitação que não é `pending`: 409 (já resolvida).
- Senha errada na eliminação: mesma resposta genérica de erro de outras rotas sensíveis (não reaproveita
  `LOGIN_BAD_CREDENTIALS` porque a pessoa já está autenticada; código próprio, ex. `WRONG_PASSWORD`).

## 7. Testes

- **Backend:** geração do protocolo (formato, sequência por ano); pacote de acesso/portabilidade contém todos os
  workspaces, perfil, sessões, tokens (sem segredo) e histórico de acesso; correção autoatendida devolve os
  links certos e não persiste `pending`; correção não autoatendida vira `pending` e aparece na fila; eliminação:
  senha errada não apaga nada; bloqueio de dono único (com e sem outros membros ativos); e-mail enviado antes do
  `DELETE`; cascade idêntico ao do admin (mesma função reaproveitada); evento no C1 sobrevive à pessoa apagada;
  fila do admin: filtro por vencida, resolver, rejeitar; permissões e allowlist de escrita.
- **Frontend:** vitest da seção "Meus dados" e da fila do admin; `tsc`, `eslint`, `i18n:check` limpos.
- **e2e no stack real:** pedir acesso e conferir o zip; pedir eliminação bloqueada por workspace compartilhado;
  criar workspace solo, pedir eliminação, confirmar que a conta some e o evento no C1 permanece.
- Antes do PR: suíte completa, `ruff`, `ty`, `check_migration_chain.py`.

## 8. Fora deste PR

- Documentos jurídicos (política de privacidade, RIPD, ROPA) — PR de documentação à parte.
- D2 (retenção/descarte geral) e D5/D6 (suboperadores, política de IA por workspace).
- Segunda etapa de confirmação por link de e-mail antes de executar a eliminação (ver §6) — decisão em aberto,
  não bloqueia esta entrega.
- Corrigir o gap pré-existente do `PATCH /api/users/me` sem senha atual — item de backlog à parte, não faz parte
  deste PR (a reautenticação criada aqui é só para a rota de eliminação).

## 9. Riscos

- **Eliminação em workspace compartilhado:** o maior risco de dado de terceiro sendo destruído. Mitigado pela
  checagem de dono único antes de qualquer exclusão.
- **Pacote de acesso/portabilidade grande:** pessoa com muitos workspaces/anos de histórico pode gerar um zip
  pesado; mesmo caminho que o `backup` já resolve hoje (streaming), sem novidade estrutural.
- **Primeiro uso de reautenticação por senha:** função pequena e isolada; não introduz um mecanismo genérico
  novo no app.
- **Prazo de 15 dias é um valor de referência**, não uma citação literal de artigo da LGPD para todo tipo de
  pedido — o texto que explica isso ao usuário faz parte do PR de documentação jurídica, não deste.
