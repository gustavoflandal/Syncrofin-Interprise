# Fase 1 — Segurança e governança: desenho

Complementa a Fase 1 de [ENTERPRISE](ENTERPRISE.md#fase-1--segurança-e-governança-46-semanas).
Cada entrega é **um PR a partir da `main`**, com migração própria (a cadeia Alembic segue de `092`;
a próxima é `093`). Ordem: C1 → C4 → C5 → C2 → C7 → D1/D3.

## Premissas

- **D-2 decidido: um servidor por cliente.** Cada cliente tem a sua própria instância (Compose ou Helm)
  e o seu próprio banco. O isolamento entre clientes é de infraestrutura; `workspace_id` isola
  áreas de trabalho **dentro de uma mesma organização**. Consequência: papéis, políticas (MFA, sessão)
  e trilha de auditoria são **da instância**, sem `tenant_id`.
- Sem dependências externas novas: tudo roda no Postgres e no Redis que já existem.
- Cada item traz testes de regressão; nenhum muda o comportamento de quem não ligou a política.

## C1 — Trilha de auditoria imutável (P0)

> ✅ **Entregue.** Uma diferença em relação ao desenho abaixo: o encadeamento por hash não acontece na gravação, e sim
> num passo de *selagem* (tarefa a cada minuto e a cada consulta), porque encadear na gravação serializaria todas as
> transações que escrevem e traria risco de *deadlock*. Detalhes em [FEATURES §9](FEATURES.md#9-trilha-de-auditoria).

**Tabela `audit_events`** (append-only): `id` (uuid), `occurred_at`, `actor_user_id` (nulo para sistema),
`actor_kind` (`user`/`api_token`/`system`), `workspace_id` (nulo para eventos da instância),
`action` (`create`/`update`/`delete`/`login`/…), `entity_type`, `entity_id`, `changes` (JSONB
`{campo: [antes, depois]}`), `ip`, `user_agent`, `request_id`, `prev_hash`/`hash`.

- **Gancho:** listener SQLAlchemy `before_flush` (mesmo modelo de `core/workspace_autostamp.py`) sobre uma
  lista explícita de modelos auditados — financeiros (transações, contas, categorias, orçamentos,
  faturas, anexos, metas, recorrências, regras) e de configuração (workspace, membros, conexões).
  Campos sensíveis (segredos, tokens, senhas) entram mascarados. Ator, IP e `request_id` vêm de um
  `ContextVar` preenchido por middleware.
- **Imutabilidade:** (1) a aplicação só tem `INSERT`/`SELECT` (sem rota ou serviço que altere); (2) *trigger*
  no Postgres que rejeita `UPDATE`/`DELETE`/`TRUNCATE` na tabela; (3) encadeamento por hash
  (`hash = sha256(prev_hash || conteúdo)`) e rota de verificação que detecta adulteração por quem tenha
  acesso direto ao banco. Um teste garante que todo modelo com `workspace_id` está na lista de auditados
  ou numa lista de exceções justificada (mesmo padrão de `test_write_permission_coverage`).
- **Consulta e exportação:** `GET /api/audit` (filtros: período, ator, entidade, ação; paginado) e
  exportação CSV; acesso restrito a `owner`/`manager` (depois, à permissão `audit.read` do C2). Tela
  "Auditoria" nas configurações do workspace.
- **Retenção:** sem exclusão pela aplicação; a política de descarte (D2) fica para depois.

*Aceite:* toda rota de escrita dos modelos auditados gera evento; `UPDATE`/`DELETE` em `audit_events`
falha mesmo com a credencial da aplicação; a verificação de hash acusa uma linha alterada por SQL direto.

## C4 — Sessões seguras (P0)

> ✅ **Entregue** ([FEATURES §10](FEATURES.md#10-sessões-seguras)). Diferenças em relação ao desenho: a validação
> consulta o **banco** (chave primária) em vez de uma lista de revogação no Redis, o que dá revogação imediata sem
> outra fonte de verdade; tokens sem `sid` são recusados em vez de aceitos por uma versão; e o app Android recebeu o
> mesmo esquema (token de renovação no corpo, guardado no Keystore).

Hoje: JWT de 24 h em `localStorage`, sem revogação. Alvo:

- Tabela `sessions` (`id`, `user_id`, `refresh_hash`, `created_at`, `last_seen_at`, `expires_at`,
  `revoked_at`, `ip`, `user_agent`, `device_label`).
- **Access token curto** (15 min, com `sid` da sessão) + **refresh token opaco** em cookie
  `httpOnly; Secure; SameSite=Strict` (o navegador nunca o lê por JavaScript), com rotação a cada uso e
  detecção de reuso (reuso revoga a sessão inteira).
- O access token passa a viver **em memória**, não em `localStorage`. O app móvel mantém o refresh no
  Keystore (já há armazenamento seguro em `mobile/src/lib/storage.ts`).
- Validação: `current_active_user` confere `sid` numa lista de revogação em Redis (revogação imediata) com
  *fallback* no banco. Rotas: listar dispositivos, encerrar uma sessão, encerrar todas as outras.
  Troca de senha encerra as demais sessões.
- Expiração por política: `SESSION_IDLE_MINUTES` e `SESSION_MAX_HOURS` (padrões definidos no PR).

*Aceite:* logout e revogação invalidam o token em até uma requisição; nada de credencial em `localStorage`.

## C5 (+ C10) — MFA obrigatório e política de senhas

> ✅ **C5 entregue** ([FEATURES §11](FEATURES.md#11-verificação-em-duas-etapas-obrigatória)). Diferenças em relação ao
> desenho: a regra é **da instância** (com escopo *todos*/*administradores*), não por papel; em vez de códigos de reserva, a
> recuperação é a **redefinição de 2FA pelo administrador**, mais o desligamento no servidor (`REQUIRE_MFA`/banco); e a
> **carência** é configurável. ✅ **C10 entregue** ([FEATURES §14](FEATURES.md#14-senhas-e-bloqueio-de-conta)): política de senhas
> no servidor (mínimo de 10, lista de senhas comuns, sem o e-mail), bloqueio progressivo por conta (teto de 1 h, sempre a mesma
> resposta de erro), desbloqueio por administrador/CLI/redefinição e aviso por e-mail de bloqueio e de dispositivo novo.

- Configuração da instância `require_mfa` (todos) e, opcional, por papel. Já existem TOTP
  (`api/two_factor.py`) e passkeys (`api/passkeys.py`).
- Com a política ativa, o login sem segundo fator devolve estado "MFA a configurar" e o token só permite
  as rotas de cadastro do fator. Período de carência configurável. Recuperação por códigos de reserva.
- C10 no mesmo PR, se couber: tamanho/lista de senhas fracas, bloqueio progressivo por conta (além do rate
  limit por IP que já existe) e aviso por e-mail de login em dispositivo novo.

## C2 — RBAC granular

> ✅ **Entregue** ([FEATURES §12](FEATURES.md#12-papéis-e-permissões-rbac)). Diferenças em relação ao desenho: os papéis
> próprios são **por workspace** (quem administra o workspace os cria, sem depender do administrador da instalação); os
> três papéis de sempre continuam como estavam, **em código**, e o papel próprio é guardado em `workspace_roles`, referenciado
> pela chave em `workspace_members.role`. A **leitura** dos dados não é uma permissão (todo membro lê); o papel **Aprovador**
> depende de o fluxo de aprovação (A6) existir: o mecanismo aceita a permissão nova quando ele chegar.

- Modelo `Role` (por instância; papéis de sistema `owner`/`editor`/`viewer`/`manager` continuam existindo
  e são imutáveis) e catálogo fixo de **permissões** `recurso.ação` (`transactions.write`,
  `transactions.export`, `invoices.approve`, `audit.read`, …). `WorkspaceMember` passa a apontar para um
  papel; migração leva os três papéis atuais para papéis de sistema com as permissões equivalentes.
- `WorkspaceContext.require_write()` vira `ctx.require("<permissão>")`; `can_write` é derivado. O teste de
  cobertura de escrita (`ALLOWLIST`) passa a exigir uma permissão declarada por rota de escrita.
- Papéis prontos: **Contador** (leitura + exportação) e **Aprovador**; a tela permite criar outros sem
  alterar código. Teste de matriz papel × rota.
- Segregação de funções (C3) e alçadas (A6) usam este catálogo depois.

## C7 — Tokens de API com escopo

> ✅ **Entregue** ([FEATURES §13](FEATURES.md#13-tokens-de-api)). Os escopos são as permissões do catálogo do C2 (sem as de
> administração), o token nunca excede o que o dono pode **naquele momento**, e as ações dele entram na auditoria como
> `api_token`.

- Tabela `api_tokens`: nome, prefixo visível, `sha256` do segredo (o valor completo aparece **uma vez**),
  escopos (subconjunto do catálogo do C2), workspace, `expires_at`, `last_used_at`, `revoked_at`.
- Autenticação por `Authorization: Bearer fbr_…`; o token nunca excede as permissões do seu criador.
  Eventos de auditoria com `actor_kind = api_token`. Rotação = criar novo e revogar o antigo.

## D1 / D3 — LGPD e registros de acesso

> ✅ **D3 entregue** ([FEATURES §15](FEATURES.md#15-registros-de-acesso)). Diferenças em relação ao desenho: em vez de só reter, o
> prazo de guarda é um **parâmetro** (183 a 3650 dias) e, vencido, o evento é **anonimizado** (a linha e os hashes ficam, para a cadeia
> do C1 continuar verificável), com o piso de 183 dias imposto pelo trigger do banco. Há consulta e CSV para o administrador e
> histórico próprio para cada pessoa. **D1 (canal do titular) segue pendente.**

- **D3:** registro de acesso à aplicação (login, falha, logout, sessão revogada, uso de token) — vira
  eventos do próprio C1, com retenção mínima de 6 meses (Marco Civil) e consulta separada.
- **D1:** canal do titular: solicitações (`acesso`, `correção`, `portabilidade`, `eliminação`) registradas
  com prazo, atendidas por exportação estruturada dos dados do usuário e por eliminação/anonimização que
  **preserva** o que a lei manda reter (a trilha de auditoria guarda o identificador, não o dado). Documentos:
  modelo de política de privacidade, RIPD e registro de operações de tratamento em `docs/lgpd/`.
- D5/D6: lista de suboperadores e chave por workspace para bloquear o envio de dados a LLMs externos.

## Fora desta fase

SAML/SCIM (C6), criptografia de campos (C9), retenção/descarte (D2) e proteção de upload (C8, parte
restante) ficam para as fases 4/5 ou para um PR avulso.

## Ordem e riscos

| Ordem | PR | Risco principal |
|-------|----|-----------------|
| 1 | C1 auditoria | Desempenho do gancho em importações grandes → gravação em lote no mesmo *flush* |
| 2 | C4 sessões | Quebra de clientes existentes (web e app) → migração com compatibilidade do JWT antigo por uma versão |
| 3 | C5 MFA | Bloquear o próprio administrador → carência + códigos de reserva + comando de emergência no servidor |
| 4 | C2 RBAC | Tocar todas as rotas de escrita → feito por permissões equivalentes primeiro, refino depois |
| 5 | C7 tokens | Vazamento de token → só o hash é guardado, escopo mínimo, expiração obrigatória |
| 6 | D1/D3 LGPD | Escopo jurídico → o código cobre o fluxo; o texto dos documentos precisa de revisão jurídica |
