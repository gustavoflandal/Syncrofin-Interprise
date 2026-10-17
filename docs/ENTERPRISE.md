# SyncroFin para uso empresarial — necessidades e plano de implementação

> Complementa o [ROADMAP](ROADMAP.md) (que trata da saúde geral do projeto) com o que falta para
> o SyncroFin ser adotado por **empresas**. Base: análise do código herdado do Securo v0.16.0.
> Onde algo é afirmado sobre o estado atual, o arquivo de origem está indicado; onde é
> "não identificado", significa que a busca no código não encontrou — vale confirmar antes de
> planejar o item.

## Status das decisões e do plano

**Decididas:** D-1 → **(a)** gestão financeira + exportação para o contador (não é sistema contábil de
partidas dobradas); D-2 → **um servidor por cliente** (instância e banco próprios; `workspace_id` isola
áreas dentro de uma organização, não clientes entre si); D-7 → **projeto independente** do upstream (ver
[ROADMAP §4](ROADMAP.md)).
**Em aberto:** D-3 (licenciamento; ver a linha D-3 da §5), D-4, D-5, D-6.

**Já entregue** (detalhes em [FEATURES](FEATURES.md)):

| Item deste plano | Situação |
|------------------|----------|
| **B3** impostos e obrigações | ✅ obrigações fiscais (DAS/DARF/ISS/INSS/ICMS) como recorrências tipadas no forecast; retenções na fatura (IRRF/ISS/PIS/COFINS/CSLL) com net_receivable e conciliação automática |
| **B4** exportação para o contador | ✅ pacote de CSVs (pt-BR, Excel), AES-256 opcional. Faltam layouts de importação de sistemas contábeis específicos |
| **A4** relatórios gerenciais | ✅ DRE/DFC, regime competência × caixa, comparativo orçado × realizado, export DFC, DFC por período |
| **E9** e-mail | ✅ SMTP para alertas, **recuperação de senha e convites** (link de uso único) |
| **E1** CI/CD | ✅ workflows de CI e de release (imagens multi-arch, chart OCI); falta criar a primeira tag |
| **E7** testes em PostgreSQL real | ✅ toda a suíte roda em Postgres + pgvector, com teste das migrações |
| **F2** webhooks de saída | ✅ endpoints por workspace, HMAC, fan-out, histórico de entregas com reentrega; integrado em transações, faturas, sync e períodos |
| **A10** conciliação de nível empresarial | ✅ aceite automático com limiar, trilha sem usuário e desfazer; múltiplos-para-um (N transações → 1 fatura) como sugestão em grupo |
| PWA | ✅ instalável; sem leitura offline de dados (por segurança) |
| **Fase 0** segredos | ✅ o sistema **não inicia** com os segredos de exemplo do repositório (backend, compose de produção e Helm); `install.sh` gera todos. Ver [DEPLOYMENT](DEPLOYMENT.md#segredos-obrigatórios-sem-valores-padrão) |
| **G4** padrões pt-BR/BRL | ✅ instância nova abre em português, reais, DD/MM/YYYY e fuso de São Paulo; categorias e carteira iniciais em português (configurável por `DEFAULT_*`) |
| **C8** cabeçalhos HTTP | ✅ CSP, nosniff, X-Frame-Options, Referrer/Permissions-Policy, COOP e HSTS (atrás de HTTPS) no nginx, fonte sem Google Fonts, proteção de upload (limite em pedaços, allowlist, magic bytes, bloqueio de SVG/HTML — `upload_guard`) e CORS configurável (`CORS_ORIGINS`) — ver FEATURES §23 |
| **C1** trilha de auditoria | ✅ append-only garantido pelo banco, cadeia de hashes, consulta e CSV; ver [FEATURES §9](FEATURES.md#9-trilha-de-auditoria). Os registros de acesso (logins e falhas) vieram no D3: [FEATURES §15](FEATURES.md#15-registros-de-acesso) |
| **C7** tokens de API | ✅ credenciais para programas: um workspace, escopos do catálogo (sem administração), nunca mais que o dono, sempre com validade, segredo mostrado uma vez, giro e revogação; ver [FEATURES §13](FEATURES.md#13-tokens-de-api) |
| **C2** RBAC granular | ✅ catálogo de 19 permissões, papéis próprios por workspace (com modelos: contador, auditor, lançador, cobrança) e os três papéis de sempre inalterados; ver [FEATURES §12](FEATURES.md#12-papéis-e-permissões-rbac). Leitura de dados segue liberada a todo membro; a aprovação (A6) virá como permissão nova |
| **C5** MFA obrigatório | ✅ regra da instância (todos ou só administradores) com prazo de carência; sessão sem segundo fator só consegue configurá-lo; ver [FEATURES §11](FEATURES.md#11-verificação-em-duas-etapas-obrigatória). A política de senhas e o bloqueio por tentativas vieram no C10 |
| **C10** senhas e bloqueio | ✅ política de senhas no servidor (mínimo 10, sem senhas comuns nem o e-mail), bloqueio progressivo por conta com teto de 1 h e resposta única de erro, desbloqueio por administrador/CLI/redefinição, e-mails de bloqueio e de login em dispositivo novo; ver [FEATURES §14](FEATURES.md#14-senhas-e-bloqueio-de-conta). O relatório de acessos veio no D3 |
| **D3** registros de acesso | ✅ registro de logins, falhas, bloqueios, sessões encerradas e uso de token de API, com consulta e CSV para o administrador e histórico próprio para cada pessoa; guarda de no mínimo 6 meses com **prazo configurável** (183 a 3650 dias) e **anonimização automática** depois dele, com o piso imposto pelo banco; ver [FEATURES §15](FEATURES.md#15-registros-de-acesso) |
| **C4** sessões seguras | ✅ token de acesso de 15 min em memória, renovação por cookie `httpOnly` revogável, lista de dispositivos; ver [FEATURES §10](FEATURES.md#10-sessões-seguras) |
| **A2** plano de contas hierárquico | ✅ categorias hierárquicas com código e natureza, editor e seletor em cascata; ver [FEATURES §16](FEATURES.md) |
| **A3** centros de custo | ✅ dimensão de custo/projeto em lançamentos com filtros e seletor; ver [FEATURES §16](FEATURES.md) |
| **A5** fechamento de período | ✅ bloqueio de escrita em meses fechados, reabertura auditada, sincronização multi-workspace; ver [FEATURES §17](FEATURES.md) |
| **A6** aprovações por alçada | ✅ alçadas por valor e categoria, segregação de funções (criador ≠ aprovador), fila de revisão; ver [FEATURES §17](FEATURES.md) |
| **A9** separação PF/PJ | ✅ transferência interworkspace com `transfer_pair_id` compartilhado; cada perna isolada no seu workspace; `is_cross_workspace_transfer`; badge ↔ PF/PJ na lista; nome do workspace parceiro no detalhe |
| **C1** trilha de auditoria imutável | ✅ `AuditEvent` append-only com trigger Postgres (rejeita UPDATE/DELETE/TRUNCATE), hash chain SHA-256, listener em 30+ modelos financeiros, `{field: [antes, após]}`, IP, segredos mascarados; API de consulta, export CSV, verificação de integridade; ver [FEATURES §9](FEATURES.md#9-trilha-de-auditoria) |
| **A1** contas a pagar e a receber | ✅ aging por bucket (corrente/30/60/90+), baixa parcial via alocação, previsão de caixa semanal/mensal; frontend `/ar-ap` com abas Visão Geral, A Receber, A Pagar, Previsão |
| **E6** testes de carga | ✅ scripts k6 em `backend/scripts/k6/` (dashboard, relatórios, transações) + `seed_perf.py` (100 k transações em escala 1×); revisão de índices; ver `docs/LOAD_TESTS.md` |

Pedidos ainda não implementados (app offline com sincronização, prevenção de lançamentos duplicados) estão na [§9](#9-demandas-registradas).

## 1. Escopo: o que significa "adequado ao uso empresarial"

O produto hoje é um **gestor financeiro de controle de caixa** (contas, transações, categorias,
orçamentos, patrimônio), com um módulo de faturas para workspaces `business`. Não é um ERP nem um
sistema contábil de partidas dobradas. "Uso empresarial" pode significar três coisas diferentes,
com custos muito distintos — a primeira decisão do plano é escolher o alvo:

| Nível | Perfil | Exigências típicas |
|-------|--------|--------------------|
| **N1 — Pequena empresa / MEI / profissional liberal** | 1–10 usuários, contador externo | Contas a pagar/receber, fluxo de caixa, DRE simples, cobrança (boleto/PIX), NFS-e, exportação para o contador, separação PF/PJ |
| **N2 — Média empresa** | 10–200 usuários, financeiro estruturado | N1 + plano de contas, centros de custo, aprovações, fechamento de período, auditoria, permissões granulares, integrações (ERP/bancos), SSO |
| **N3 — Corporativo** | 200+ usuários, TI/compliance | N2 + SAML/SCIM, SLA/HA/DR, trilha de auditoria imutável, segregação de funções, certificações (SOC 2/ISO 27001), suporte 24×7 |

**Recomendação:** mirar **N1 → N2** (onde o produto já tem base: workspaces `business`, faturas,
OIDC, papéis, fiscal por jurisdição) e tratar N3 como consequência de maturidade, não como meta
inicial. Posicionar o produto como **gestão financeira e tesouraria com exportação para a
contabilidade**, e **não** como substituto do sistema contábil (ver decisão D-1 na §5).

## 2. O que já existe (ponto de partida)

| Capacidade | Onde | Observação |
|-----------|------|-----------|
| Workspaces `personal`/`business`, papéis `owner`/`editor`/`viewer`/`manager` | `models/workspace.py`, `core/workspace_context.py` | Papéis fixos e amplos; sem permissão por recurso/ação |
| Módulos por tipo de workspace (faturas só em `business`) | `services/module_service.py` | Extensível por política |
| Faturas com direção `receivable`/`payable`, status por decisão, alocações de pagamento, PDF, link público, anexos | `models/invoice.py`, `services/invoice_*` | `payable` está no esquema como direção declarada; a maturidade da UI/fluxo de contas a pagar deve ser confirmada |
| Documentos fiscais por jurisdição (CPF/CNPJ etc.), payees com IDs fiscais | `app/fiscal/`, `models/payee.py` | Valida/formata; **não emite** documentos fiscais |
| Recorrências, orçamentos, metas, projeções | `services/recurring_*`, `budget_service` | Base para previsão de caixa |
| Conciliação com regras, sugestões e histórico | `services/reconciliation_*` | `ReconciliationEvent` é a única trilha de auditoria estruturada identificada |
| Sincronização bancária (Pluggy/Open Finance, PSD2, SimpleFIN) | `providers/`, `connection_service` | Somente leitura de dados |
| SSO OIDC com sincronização de papéis, 2FA, passkeys, rate limit de login | `api/oidc_auth.py`, `two_factor.py`, `passkeys.py`, `core/rate_limit.py` | SAML/SCIM não existem |
| Multimoeda, câmbio | `fx_rate_service` | |
| Backup ZIP criptografado, exportação CSV | `services/backup_service.py`, `api/export.py` | Backup é por usuário/workspace, não operação de DR |
| API OpenAPI (`/api/docs`), agentes/MCP | `app/main.py`, `mcp_server/` | Autenticação apenas por JWT de usuário |
| Helm chart, Compose, lockfile com hash | `charts/syncrofin/`, `docker-compose*.yml` | Sem CI/imagens publicadas hoje |

## 3. Necessidades (gaps) por eixo

Convenção: **P0** pré-requisito para qualquer piloto empresarial · **P1** necessário para N1 · **P2** necessário
para N2 · **P3** N3/diferencial. Esforço: **S** ≤ 1 semana · **M** 1–3 · **L** 3–6 · **XL** > 6
(1 desenvolvedor, incluindo testes e documentação).

### A. Núcleo financeiro empresarial

| ID | Necessidade | Estado atual | Prior. | Esforço |
|----|-------------|--------------|--------|---------|
| A1 | **Contas a pagar e a receber** completas: vencimento, baixa parcial/total, aging, fornecedores, previsão de caixa por vencimento | ✅ `GET /api/ar-ap/overview` (aging por bucket), `/titles` (lista paginada por direção/estado, baixa via alocação), `/forecast` (previsão semanal/mensal); frontend `/ar-ap` com abas Visão Geral, A Receber, A Pagar, Previsão; componentes `AgingCard`, `TitlesList`, `CashFlowForecast` | P1 | L |
| A2 | **Plano de contas** hierárquico (além das categorias planas + grupos) com natureza (receita/despesa/custo) e código | ✅ Categorias hierárquicas com código contábil e natureza (receita/despesa/custo); editor e seletor em cascata; ver [FEATURES §16](FEATURES.md) | P2 | M |
| A3 | **Centros de custo / projetos / departamentos** como dimensão de lançamento e de orçamento | ✅ Dimensão de custo/projeto em lançamentos, orçamentos e recorrências; filtros em relatórios; seletor na transação; ver [FEATURES §16](FEATURES.md) | P2 | L |
| A4 | **Relatórios gerenciais**: DRE, fluxo de caixa (DFC direto), competência × caixa, comparativo orçado × realizado por centro de custo | ✅ DRE e DFC (direto), regime competência × caixa, comparativo orçado × realizado, export PDF/XLSX; `reports.tsx` + `report_service.py`; ver [FEATURES §4](FEATURES.md) | P1 | L |
| A5 | **Fechamento de período** (bloqueio de lançamentos em meses fechados, reabertura auditada) | ✅ `period_closes` + guard em escrita/sync; UI em `/workspace/periods`; ver [FEATURES §16](FEATURES.md#16-fechamento-de-período) | P2 | M |
| A6 | **Fluxo de aprovação** (alçadas por valor/categoria para pagamentos e lançamentos) | ✅ `workspace_approval_rules` + `approval_events`; aviso na criação; UI em `/workspace/approvals`; ver [FEATURES §17](FEATURES.md#17-aprovações-por-alçada) | P2 | L |
| A7 | **Multiempresa consolidada** (visão agregada de vários workspaces `business`, transferências intercompany, eliminação) | ✅ GET /api/consolidated/dre com eliminação automática de intercompany; frontend /consolidated; testes | P2 | XL |
| A8 | **Rateio e provisões** (rateio entre centros de custo, despesas provisionadas/diferidas) | ✅ `cost_center_allocations` (rateio por % ou valor, soma = valor da transação) + `accrual_schedules`/`accrual_entries` (provisão/diferimento mensal lançado por Celery no dia 1); UI em `/accruals` e seção *Rateio* na transação; ver [FEATURES §24](FEATURES.md#24-rateio-e-provisões) | P3 | L |
| A9 | **Separação PF/PJ** com transferências entre workspaces sem misturar dados | ✅ Feito: `create_cross_workspace_transfer` em `transaction_service` cria débito no workspace de origem e crédito no destino, vinculados por `transfer_pair_id` + `is_cross_workspace_transfer=true`; `transfer-dialog.tsx` expõe seletor de workspace-destino quando o usuário tem acesso a múltiplos workspaces; label especial na lista de transações | P1 | M |
| A10 | Conciliação bancária de nível empresarial (múltiplos-para-um, tolerância de valor/data, baixa de títulos por extrato) | ✅ Aceite automático com limiar de confiança, trilha sem usuário, desfazer; sugestões N:1 (múltiplas transações → 1 fatura) como grupo; ver [FEATURES §7](FEATURES.md) | P2 | M |

### B. Fiscal e cobrança (Brasil)

| ID | Necessidade | Estado atual | Prior. | Esforço |
|----|-------------|--------------|--------|---------|
| B1 | **Emissão de NFS-e/NF-e** via provedor (Focus NFe, eNotas, PlugNotas, etc.) — nunca emissor próprio | ✅ `FiscalProviderConfig` + `FiscalEmission`; Focus NFe adapter; `POST …/invoices/{id}/emit-nfe`; status badge + refresh/cancel no detalhe da fatura; config no workspace-settings | P1 | XL |
| B2 | **Cobrança por boleto e PIX** com baixa automática (Asaas, Inter, Cora, PagBrasil…) e webhook de liquidação | ✅ `BillingProviderConfig` + `BillingCharge`; adaptador Asaas (boleto e PIX dinâmico, dedup de pagador, QR Code); webhook `POST /api/billing/webhook/{provider}/{workspace_id}` com baixa automática (Transaction + InvoiceAllocation); permissões `billing.read`/`billing.manage`; seção de config em workspace-settings; seção de cobrança com status badge, link boleto, PIX copia-e-cola e ações de refresh/cancelar em invoice-detail | P1 | L |
| B3 | **Impostos e obrigações**: DAS/Simples, DARF, ISS como recorrências/previsão de caixa; retenções na fatura | ✅ Obrigações fiscais como recorrências tipadas com projeção no forecast AR/AP; retenções na fatura (IRRF/ISS/PIS/COFINS/CSLL) com `net_receivable` no forecast e `withholding_ratios` na conciliação; ver [FEATURES §18](FEATURES.md) | P2 | M |
| B4 | **Exportação para o contador** (lançamentos por período, plano de contas, layouts de importação de sistemas contábeis comuns, SPED apenas via terceiros) | ✅ Feito: ZIP com 6 CSVs pt-BR + `LEIA-ME.txt`; plano de contas com código contábil e natureza (grupo); NF-e (chave de acesso, número, série) em `titulos.csv`; novo endpoint `GET /export/accountant/xlsx` devolve planilha XLSX com uma aba por arquivo | P1 | M |
| B5 | Importação de **NF-e (XML)** de compra e extratos OFX/CNAB de bancos BR | ✅ `POST /workspaces/{id}/nfe/preview` + `/import`; CNAB240/CNAB400 detectados automaticamente no importador de transações; título a pagar criado via chave de acesso (idempotente) | P2 | M |
| B6 | Retenção documental fiscal (guarda ≥ 5 anos) com anexos imutáveis | ✅ `InvoiceAttachment.is_locked/locked_at/locked_by/retention_until`; `POST …/attachments/{id}/lock`; 403 em delete/modify de anexo travado; ícone de cadeado + badge de retenção + botão travar no detalhe da fatura; ver [FEATURES §19](FEATURES.md#19-retencao-documental-fiscal) | P2 | M |

### C. Segurança, governança e identidade

| ID | Necessidade | Estado atual | Prior. | Esforço |
|----|-------------|--------------|--------|---------|
| C1 | **Trilha de auditoria imutável** (quem/quando/o quê/antes→depois, IP) para toda escrita financeira e de configuração | ✅ `AuditEvent` append-only (migração 093); trigger Postgres rejeita UPDATE/DELETE/TRUNCATE; hash chain SHA-256 via `audit_events_seal()`; listener `after_flush` em 30+ modelos; `changes` JSONB com antes/depois, segredos mascarados; API `GET /api/audit` (filtros por data/ator/entidade/ação) + export CSV + verificação de cadeia; frontend `/audit`; sealing periódico via Celery; ver [FEATURES §9](FEATURES.md#9-trilha-de-auditoria) | P0 | L |
| C2 | **RBAC granular** com papéis customizáveis (ex.: contador somente-leitura, aprovador, tesoureiro) e permissões por ação/recurso | ✅ Catálogo de 19+ permissões; papéis customizáveis por workspace com modelos (contador, auditor, lançador, cobrança); `api/roles.py` + `services/role_service.py` + `RolesCard` no frontend; ver [FEATURES §12](FEATURES.md#12-papéis-e-permissões-rbac) | P1 | L |
| C3 | **Segregação de funções** (quem cria ≠ quem aprova ≠ quem paga) | ✅ Feito: flag `segregation_enabled` no workspace (migração 118); criador não pode rejeitar a própria tx (deve cancelar); liquidação (`settled_by_user_id`, `settled_at`) por terceiro diferente do criador e do aprovador; endpoint `POST /approvals/{id}/settle`; toggle em workspace-settings; badges na fila de aprovação | P2 | M |
| C4 | **Gestão de sessão**: refresh token, revogação, lista de dispositivos, expiração por política; sair do JWT em `localStorage` | ✅ Feito: access token em memória (15 min, não em localStorage); refresh token httpOnly cookie com rotação a cada uso e detecção de replay; `GET /sessions` lista dispositivos com device_label/ip/auth_method; `DELETE /sessions/{id}` e `POST /sessions/revoke-others`; `SessionsDialog` no frontend; expiração absoluta configurável (`SESSION_EXPIRE_DAYS`) | P0 | M |
| C5 | **MFA obrigatório por política** do workspace/instância | ✅ Instância via admin panel (`mfa_required` + `mfa_required_scope` + `mfa_grace_days`) já existia; adicionado campo `mfa_required` no modelo `Workspace` (migração 113) + enforce em `workspace_context.py` + toggle em workspace-settings | P1 | S |
| C6 | **SAML 2.0** e **SCIM** (provisionamento/desprovisionamento automático) | ✅ SAML SP com python3-saml (metadata, login, ACS, SLO); SCIM 2.0 Users (list/get/create/replace/patch/delete); migração 120; botão no login, callback page; i18n en/pt-BR/es | P2 | L |
| C7 | **Tokens de API/serviço** com escopo, expiração e rotação (para integrações) | ✅ Feito: modelo `ApiToken` (`scopes` JSONB, `expires_at`, `revoked_at`, `prefix`); `api_token_service` (create/rotate/revoke/authenticate); endpoints em `POST /api/api-tokens` + rotate + revoke; autenticação Bearer em `core/auth.py` (`looks_like_api_token` → verifica hash, workspace e escopo); um token não pode criar outro (`_by_a_person`); máx. 100 tokens/workspace, máx. 365 dias | P1 | M |
| C8 | Endurecimento HTTP: CSP, HSTS, headers de segurança, CORS restrito, proteção de upload (antivírus/limites) | ✅ Feito: `security-headers.inc.template` no nginx com CSP (script/style/img/connect/frame/worker), HSTS condicional (somente HTTPS), X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy strict-origin, Permissions-Policy, COOP same-origin; CORS restrito a `FRONTEND_URL` ou a `CORS_ORIGINS`; `server_tokens off`; upload limitado por `client_max_body_size` (`UPLOAD_MAX_BODY_SIZE`) no nginx e validado no backend por `core/upload_guard.py` (FEATURES §23) | P0 | S |
| C9 | Criptografia de campos sensíveis em repouso (tokens de bancos, segredos de integrações) e gestão de chaves/rotação | ✅ Feito (PR #7): `totp_secret_enc` (migração 107) + Pluggy `item_id_enc`; Fernet/PBKDF2 via `agents/services/crypto.py`; fallback plaintext para rows antigos | P1 | M |
| C10 | Política de senhas, bloqueio por tentativas, notificação de login suspeito | ✅ Feito ([FEATURES §14](FEATURES.md#14-senhas-e-bloqueio-de-conta)); antes, só rate limit por IP no login | P2 | M |
| C11 | Pentest independente e revisão de dependências contínua (SCA/SAST no CI) | ✅ Parcial: SCA com `pip-audit` (Python) e `npm audit` (frontend) no CI (job `audit`, informacional); SAST Python com `bandit` adicionado ao mesmo job; pentest independente pendente | P1 | M |

### D. Conformidade e privacidade

| ID | Necessidade | Estado atual | Prior. | Esforço |
|----|-------------|--------------|--------|---------|
| D1 | **LGPD**: mapeamento de dados pessoais, base legal, RIPD, política de privacidade e termos, canal do titular (acesso/correção/eliminação/portabilidade) | ✅ Canal do titular feito: `api/data_requests.py` + `services/data_subject_request_service.py` — acesso/portabilidade com pacote de exportação, correção self-service, eliminação em cascata com re-autenticação; RIPD/política de privacidade/termos pendentes (itens legais) | P0 | M |
| D2 | **Retenção e descarte** configuráveis por tipo de dado; anonimização | ✅ `DataRetentionPolicy` por workspace (migração 119) com prazos configuráveis (transações 7a, anexos 5a, auditoria 10a); anonimização ou exclusão automática; purga diária + manual; ver [FEATURES §21](FEATURES.md#21-retenção-de-dados) | P2 | M |
| D3 | **Registros de acesso** à aplicação (Marco Civil: 6 meses) com guarda protegida | ✅ Feito ([FEATURES §15](FEATURES.md#15-registros-de-acesso)); antes, logs de aplicação básicos | P1 | S |
| D4 | Consentimento e transparência do Open Finance (escopo, prazo, revogação) refletidos na UI | Delegado ao Pluggy | P2 | S |
| D5 | Acordo de processamento de dados (DPA) com suboperadores (Pluggy, provedores de LLM, câmbio, cotações) | ✅ `docs/DPA.md`: tabela de suboperadores (Pluggy, Enable Banking, Focus NFe, eNotas, PlugNotas, Asaas, Anthropic), base legal, transferências internacionais, retenção e canal do DPO | P1 | S |
| D6 | **Agentes de IA**: política de dados por workspace (quais dados podem sair para LLMs externos), desabilitar por workspace, log de prompts/uso | ✅ Feito: `agents_enabled` (kill-switch por workspace, migração 114) + `agent_data_policy` (JSONB com allow_identity/balances/transactions/payees/invoices); `chat.py` verifica `agents_enabled` e retorna 403 `AI_AGENTS_DISABLED`; `context_service.build_context_primer` filtra categorias conforme política; toggle + painel de política granular em workspace-settings; uso de tokens registrado em `agent_llm_usage` (pré-existente) | P1 | M |

### E. Escalabilidade, confiabilidade e operação

| ID | Necessidade | Estado atual | Prior. | Esforço |
|----|-------------|--------------|--------|---------|
| E1 | **CI/CD** com imagens versionadas e assinadas, release notes, rollback | ✅ `.github/workflows/ci.yml` (lint, tipos, testes em Postgres), `release.yml` (imagens multi-arch `ghcr.io/gustavoflandal/syncrofin-enterprise-*`, chart OCI) e `mobile.yml` (build Android); falta criar a primeira tag | P0 | M |
| E2 | **Backups automatizados + PITR** do Postgres e **teste periódico de restauração**; definição de RPO/RTO | ✅ Feito: perfil `backup` do `docker-compose.prod.yml` com `db-backup` (pg_dump+gzip diário), `db-basebackup` (pg_basebackup semanal com poda) e arquivamento contínuo de WAL (`archive_timeout=300`, volume `pgwal`) → PITR; `backend/scripts/restore_drill.sh` restaura num Postgres temporário (opção `--target-time`), valida (`alembic_version`, `users`, `workspaces`, cadeia de migrações) e mede RTO/RPO; Helm: `backup.enabled` (CronJobs + PVC + WAL no StatefulSet). Metas RPO ≤ 15 min, RTO ≤ 2 h; ver ADMIN §6 | P0 | M |
| E3 | **Armazenamento de objetos (S3/compatível)** para anexos e conhecimento (elimina RWX/volume único) | ✅ Feito: `providers/s3_storage.py` com boto3 async, SSE-S3, presigned URLs; configurável via `STORAGE_PROVIDER=s3` + `STORAGE_S3_*`; compatível com MinIO, R2, Spaces | P1 | M |
| E4 | **Alta disponibilidade**: Postgres gerenciado/replicado + PgBouncer, Redis com persistência/Sentinel, backend/worker com réplicas, beat singleton | ✅ PDB, rolling update `maxUnavailable:0`, anti-afinidade, readiness `/api/ready`, pool tuning, Redis AOF, beat singleton protegido; ver [FEATURES §20](FEATURES.md#20-alta-disponibilidade-e-operação) | P2 | L |
| E5 | **Observabilidade**: logs estruturados com request-id, métricas Prometheus, tracing (OpenTelemetry), alertas, health/readiness reais | ✅ logs JSON estruturados (`LOG_FORMAT=json`, `core/logging_config.py`) com request-id e `trace_id`/`span_id`; `/api/health` (liveness) e `/api/ready` (readiness DB+Redis, 503 em falha); métricas Prometheus em `/api/metrics` + `ServiceMonitor` no chart (`metrics.serviceMonitor.enabled`); tracing OpenTelemetry opcional via `OTEL_EXPORTER_OTLP_ENDPOINT` (`core/tracing.py`) | P1 | M |
| E6 | **Testes de carga e capacidade** (milhões de transações, dezenas de usuários simultâneos), revisão de índices/consultas de dashboard e relatórios | ✅ Scripts k6 em `backend/scripts/k6/` (dashboard: 50 VUs p95 < 500 ms; relatórios: 20 VUs p95 < 2 s; transações mistas: 30 VUs p95 < 800 ms); `seed_perf.py --scale 10` gera ~1 M de transações; guia em `docs/LOAD_TESTS.md` | P1 | M |
| E7 | **Testes contra PostgreSQL real** no CI (migrações, collation, pgvector) | ✅ CI roda a suíte inteira em `pgvector/pgvector:pg16`; migrações testadas na cadeia completa; sem fallback SQLite | P0 | M |
| E8 | Migrações sem indisponibilidade e estratégia de rollback | ✅ Advisory lock `pg_advisory_lock(42)` + timeouts no Alembic; serviço `db-migrate` separado no Compose; Job Helm já existente; ver [FEATURES §20](FEATURES.md#20-alta-disponibilidade-e-operação) | P2 | M |
| E9 | **Notificações**: envio de e-mail (SMTP/API), webhooks de alerta; recuperação de senha por e-mail | ✅ `email_service.py` com SMTP (`SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASS`); templates para recuperação de senha, convites, bloqueio de conta e login em dispositivo novo; `password_reset.py` com link de uso único em background (não revela quem tem conta) | P0 | M |
| E10 | Rate limit e cotas por tenant/token em endpoints caros | ✅ Feito: `RateLimiter` Redis sliding-window aplicado em import, export, backup, agents-chat; configurável por instância | P2 | S |
| E11 | Fila de trabalhos idempotente com retentativas e fila morta (sync, importações, exportações grandes) | ✅ `task_acks_late`, `reject_on_worker_lost`, retentativas com backoff em sync/recurring/notification tasks; ver [FEATURES §20](FEATURES.md#20-alta-disponibilidade-e-operação) | P2 | M |

### F. Integrações e ecossistema

| ID | Necessidade | Estado atual | Prior. | Esforço |
|----|-------------|--------------|--------|---------|
| F1 | **API pública versionada** (`/api/v1`), contrato estável, paginação/filtragem consistentes, SDK ou coleção Postman | ✅ `GET /api/v1/{workspaces,accounts,transactions,invoices,payees,categories}`; paginação `page+limit+total+items` uniforme; docs interativos em `/api/v1/docs`; changelog de estabilidade em `docs/API_CHANGELOG.md` | P1 | L |
| F2 | **Webhooks de saída** (transação criada, fatura paga, sync falhou) com assinatura e reentrega | ✅ Endpoints por workspace, assinatura HMAC, fan-out, histórico de entregas com reentrega; integrado em transações, faturas, sync e períodos; tela `/workspace/webhooks`; ver [FEATURES §8](FEATURES.md) | P2 | M |
| F3 | Conectores ERP/contábeis (Omie, Conta Azul, Bling, Alterdata, Domínio) — via API ou arquivos | ✅ Camada de abstração `backend/app/erp/` (Protocol `ErpConnector` + registro por nome), conector **Omie** (importa plano de contas e beneficiários; envia faturas como contas a pagar/receber, idempotente, limite de 3 req/s) e esqueleto do **Conta Azul** (OAuth2 pendente). Credenciais cifradas, mapeamento local↔externo (`erp_entity_mappings`), histórico de execuções, sync em Celery (`erp_tasks`), tela `/workspace/erp`, permissões `erp.read`/`erp.manage`. Bling, Alterdata e Domínio ficam para novos adaptadores sobre o mesmo contrato | P2 | XL |
| F4 | **Pagamentos** (iniciação de PIX/TED via API bancária) com dupla aprovação | ✅ `PaymentOrder` + `PaymentApprovalEvent` (migração 122); Protocol `PaymentProvider` + adaptador `sandbox` (adaptadores bancários reais ainda por escrever); dupla aprovação sempre exigida (criador ≠ aprovador 1 ≠ aprovador 2 ≠ quem envia); idempotência por `idempotency_key`; webhook `POST /api/payments/webhook/{provider}/{workspace_id}` com reconsulta ao provedor; tarefa Celery `check_pending_payments` a cada 5 min; lançamento de débito e baixa da fatura na confirmação; permissões `payments.read/write/approve/send`; página `/payments` | P3 | XL |
| F5 | Importação assistida de dados de outros sistemas/planilhas (assistente de migração) | ✅ Feito: aba "Migração" em `/import?tab=migration` com wizard 3 passos (categorias → beneficiários → transações); `POST /api/categories/import` e `POST /api/payees/import` aceitam CSV com header flexível (pt-BR/en), pulam linhas duplicadas, retornam created/skipped/failed; template CSV para download embutido | P1 | M |

### G. Produto, suporte e go-to-market

| ID | Necessidade | Prior. | Esforço |
|----|-------------|--------|---------|
| G1 | Onboarding de empresa (assistente: dados da empresa, regime tributário, plano de contas modelo, usuários, bancos) | ✅ Feito: wizard 4 passos em `frontend/src/pages/onboarding-empresa.tsx` (dados legais, regime tributário, plano de contas modelo, usuários iniciais); seed empresarial via `POST /api/workspaces/{id}/onboarding` com validação de CNPJ e criação de categorias contábeis | P1 | M |
| G2 | Perfis de tela por papel (financeiro, diretoria, contador) e relatórios exportáveis em PDF/XLSX com identidade da empresa | ✅ Feito: botões PDF/XLSX na página de relatórios (Net Worth, Income/Expenses) com `reports.downloadFile`; upload de logo do workspace em `workspace-settings.tsx`; campo `logo_storage_key` no schema; i18n (en, pt-BR, es) | P2 | L |
| G3 | Documentação de usuário e administrador em pt-BR; guias de implantação | ✅ Feito: `docs/MANUAL.md` (manual do usuário gerado do help inline, 148K); `docs/DEPLOYMENT.md` (deploy/update); `docs/ADMIN.md` (guia do administrador: usuários, workspaces, backup, auditoria, LGPD, monitoramento) | P1 | M |
| G4 | Padrões pt-BR/BRL por padrão; revisão de terminologia contábil brasileira (ver ROADMAP item 16–17) | ✅ Feito: `DEFAULT_LANGUAGE='pt-BR'` com detector de navegador (`i18n.ts`), `default_currency='BRL'` no `core/config.py`; sem referências ao produto upstream nos locales | P0 | M |
| G5 | Modelo de licenciamento e suporte (ver D-3 e D-4 abaixo), SLA, canal de suporte, política de versionamento/LTS | ✅ Feito: `docs/SUPPORT.md` — licenciamento (AGPL herdado + propriedade Enterprise), SLA por severidade (P0 24h → P3 backlog), LTS de 12 meses, política semver, canais de suporte e privacidade | P1 | M |
| G6 | Acessibilidade (WCAG 2.1 AA — o frontend já usa `eslint-plugin-jsx-a11y`) e desempenho em telas grandes | ✅ Feito (acessibilidade): link "pular para o conteúdo", contraste AA nos tokens de cor, `jsx-a11y` recommended (como aviso; ~70 pendências legadas), testes axe (`vitest-axe`), `scope="col"` nos `TableHead`, rótulos de navegação. Desempenho em telas grandes segue em aberto | P3 | M |

## 4. Plano de implementação

Premissas: **1–2 desenvolvedores em tempo integral**, alvo **N1 → N2**, estimativas em semanas com
margem de incerteza (±30 %). As fases 3, 4 e 5 podem correr **em paralelo** com dois
desenvolvedores. Cada fase termina com uma versão publicada (tag) e critérios de aceite verificáveis.

### Visão geral

```
Fase 0  Fundação            ██                         2–3 sem
Fase 1  Segurança/Governança  ████                       4–6 sem
Fase 2  Núcleo financeiro       ████████                   8–12 sem
Fase 3  Fiscal e cobrança BR            ██████               6–10 sem   ┐ paralelizáveis
Fase 4  Escala e confiabilidade         ████                 4–6 sem    │ com 2 devs
Fase 5  Integrações e ecossistema         ██████             6–8 sem    ┘
Fase 6  Piloto e endurecimento                  ███          4 sem
Total sequencial: 34–49 semanas · com 2 devs em paralelo: ~6–8 meses
```

### Fase 0 — Fundação (2–3 semanas)

*Objetivo:* ter um projeto que constrói, testa e publica sozinho, com padrões brasileiros.

| Entregável | Itens | Critério de aceite |
|------------|-------|--------------------|
| Pipeline de CI/CD, imagens e chart publicados, primeira tag | E1, ROADMAP 1–3 | Push em `main` roda lint/tipos/testes; tag `v*` publica imagens; `install.sh` funciona em host limpo |
| Testes em PostgreSQL real no CI; testes frágeis corrigidos | E7, ROADMAP 13–14 | CI verde e estável em 10 execuções seguidas |
| Padrões pt-BR/BRL; textos revisados | G4 | Instância nova abre em pt-BR/BRL com categorias padrão em português |
| Endurecimento de compose/segredos e headers HTTP | C8, ROADMAP 6–7 | Subida falha com segredos padrão fora de `DEBUG`; scanner de headers sem achados críticos |
| Envio de e-mail (SMTP/provedor transacional) | E9 | Recuperação de senha e convite de usuário chegam por e-mail |

### Fase 1 — Segurança e governança (4–6 semanas)

*Objetivo:* tornar seguro colocar dados de terceiros e responder "quem fez isso?".

| Entregável | Itens | Critério de aceite |
|------------|-------|--------------------|
| **Trilha de auditoria** (tabela append-only, gancho de escrita, UI de consulta e exportação) | C1, D3 | 100 % das rotas de escrita financeira/config geram evento; tentativa de edição/remoção de evento é impossível pela aplicação |
| Sessões seguras (cookie `httpOnly` ou refresh token, revogação, lista de dispositivos) | C4 | Logout/revogação invalida sessão imediatamente; token não fica em `localStorage` |
| MFA obrigatório por política; política de senhas | C5, C10 | Workspace com política ativa não permite acesso sem 2º fator |
| **RBAC granular** (papéis customizados, permissões por ação) | C2 | Papel "contador" (leitura + exportação) e "aprovador" configuráveis sem alterar código; testes de matriz de permissões |
| Tokens de API com escopo | C7 | Token de leitura não consegue escrever; rotação e revogação funcionam |
| **Canal do titular (LGPD)** — acesso, portabilidade, correção e eliminação; fila do administrador; protocolo e prazo | D1 | ✅ Canal do titular implementado; `docs/lgpd/` (jurídico), D5/D6 e D2 ficam para depois |

### Fase 2 — Núcleo financeiro empresarial (8–12 semanas)

*Objetivo:* atender a rotina do financeiro de uma pequena/média empresa.

| Entregável | Itens | Critério de aceite |
|------------|-------|--------------------|
| **Contas a pagar/receber** unificadas (títulos, vencimento, baixa parcial, aging, agenda) | A1 | ✅ Feito (PR #9): lista paginada por direção/estado, baixa rápida via alocação, previsão de caixa semanal/mensal (`/api/ar-ap/titles` + `/api/ar-ap/forecast`); página com 4 tabs |
| **Plano de contas** e **centros de custo** (dimensões em transações, splits, orçamentos, recorrências) | A2, A3 | Todo lançamento aceita centro de custo; relatórios filtram e agrupam por ele |
| **DRE e DFC** (competência × caixa, orçado × realizado) | A4 | DRE fecha com o razão de transações; testes de reconciliação de totais |
| **Fechamento de período** com reabertura auditada | A5 | Escrita em período fechado é rejeitada (API e importações/sync) |
| **Aprovações por alçada** e segregação de funções | A6, C3 | Pagamento acima da alçada exige aprovador diferente do criador |
| Separação PF/PJ e vínculo entre workspaces | A9 | Transferência PF↔PJ registra as duas pontas sem expor dados de um lado ao outro |
| Onboarding de empresa e migração de dados | G1, F5 | Empresa nova configurada (plano de contas modelo + usuários + banco) em < 1 h |
| **Exportação ao contador** | B4 | Arquivo por período aceito no sistema contábil do piloto sem retrabalho manual |

### Fase 3 — Fiscal e cobrança BR (6–10 semanas)

| Entregável | Itens | Critério de aceite |
|------------|-------|--------------------|
| **Provedor de NFS-e/NF-e** (abstração `FiscalEmitter` + 1 provedor real; status, cancelamento, XML/PDF anexados) | B1, B6 | Emissão de NFS-e em homologação e produção a partir de uma fatura; XML arquivado e imutável |
| **Cobrança boleto/PIX** com webhook de liquidação e baixa automática | B2, F2 | Pagamento liquidado no provedor baixa a fatura sem intervenção; reentrega idempotente |
| Obrigações/impostos como agenda e retenções na fatura | B3 | DAS/ISS/DARF aparecem na previsão de caixa; retenções calculadas na fatura |
| Importação de NF-e XML e CNAB | B5 | Nota de compra vira título a pagar com fornecedor e vencimentos |

### Fase 4 — Escala e confiabilidade (4–6 semanas, paralela à 3 e 5)

| Entregável | Itens | Critério de aceite |
|------------|-------|--------------------|
| Armazenamento S3 para anexos/conhecimento | E3 | Backend/worker sem volume compartilhado; migração dos anexos existentes documentada |
| Backups automáticos, PITR e **teste de restauração** agendado | E2 | RPO ≤ 15 min e RTO ≤ 2 h demonstrados em exercício |
| Observabilidade (logs estruturados, métricas, tracing, alertas, readiness) | E5 | Painel com latência/erros por rota e alerta de falha de sync/worker |
| Testes de carga e otimização | E6 | Metas: p95 < 500 ms nas listagens/dashboard com 1 M de transações e 50 usuários simultâneos |
| HA opcional no chart (réplicas, PgBouncer, Redis persistente, beat singleton) | E4, E8, E11, E10 | Falha de um pod não interrompe o serviço; migração sem indisponibilidade |

### Fase 5 — Integrações e ecossistema (6–8 semanas, paralela)

| Entregável | Itens | Critério de aceite |
|------------|-------|--------------------|
| **API pública `/api/v1`** versionada, documentada, com coleção/SDK | F1 | Contrato coberto por testes de compatibilidade; política de depreciação publicada |
| Webhooks de saída assinados | F2 | Assinatura HMAC, reentrega com backoff, painel de entregas |
| **SAML 2.0 e SCIM** | C6 | ✅ SP SAML + SCIM Users CRUD; provisionamento reflete no IdP |
| 1–2 conectores ERP/contábeis priorizados pelo piloto | F3 | Sincronização bidirecional do escopo acordado, com logs e reprocessamento |
| Relatórios PDF/XLSX e perfis por papel | G2 | ✅ Botões de exportação PDF/XLSX; logo da empresa nos relatórios; permissão `export.read` |

### Fase 6 — Piloto e endurecimento (4 semanas)

- Piloto com **1–3 empresas reais** (idealmente de perfis distintos: serviços, comércio, contador
  atendendo vários clientes), com dados reais sob DPA.
- **Pentest independente** (C11), correção dos achados críticos/altos.
- Documentação de usuário e administrador (G3), runbooks de operação e incidentes, SLA/suporte (G5).
- **Critério de saída (go-live):** checklist da §7 integralmente atendido.

## 5. Decisões arquiteturais e de negócio a tomar cedo

| # | Decisão | Opções | Recomendação |
|---|---------|--------|--------------|
| D-1 | **Escopo contábil** ✅ *decidido: (a)* | (a) gestão financeira + exportação ao contador; (b) razão de partidas dobradas completo | **(a)**. Partidas dobradas muda o núcleo (todo lançamento vira débito/crédito), conflita com o modelo atual de transação por conta e faz o produto competir com ERPs. Reavaliar após o piloto |
| D-2 | **Modelo de implantação** ✅ *decidido: um servidor por cliente* | Self-hosted por cliente · SaaS multi-tenant · SaaS single-tenant por cliente | Começar **single-tenant por cliente** (o Compose/Helm já suportam) e evoluir para multi-tenant quando houver escala; o isolamento por `workspace_id` é lógico, não é fronteira de segurança forte entre clientes distintos |
| D-3 | **Licenciamento** | Manter AGPL · licença comercial dupla | O código herdado é AGPL-3.0 de terceiros: **não é possível relicenciar** sem consentimento dos autores. Oferecer SaaS com modificações **obriga a publicar o código-fonte**. Modelo viável: serviços (implantação, suporte, customização) sobre código aberto |
| D-4 | **Fiscal** | Emissor próprio · provedor terceiro | **Provedor terceiro** (abstração `FiscalEmitter`). Emissão própria exige certificação por município/UF e manutenção constante |
| D-5 | **Autorização** | RBAC · ABAC · RBAC + regras de alçada | **RBAC + alçadas** (modelo `Permission` × `Role` por workspace) |
| D-6 | **Trilha de auditoria** | Evento por escrita (append-only) · event sourcing | **Append-only por evento**, sem reescrever o núcleo |
| D-7 | **Acompanhar o upstream?** ✅ *decidido: independente* | Manter sincronizado · divergir | ~~Decidir antes da Fase 2~~ Decidido: as mudanças de A1–A6 tocam os mesmos arquivos grandes do upstream (ver ROADMAP §4) |

## 6. Pontos de partida no código (para quem for implementar)

| Item | Onde começar |
|------|--------------|
| Auditoria (C1) | Listener `before_flush`/`after_flush` do SQLAlchemy nos moldes de `core/workspace_autostamp.py`; nova tabela `audit_events` (migração `091+`) e router `api/audit.py` |
| RBAC (C2) e alçadas (A6/C3) | `WORKSPACE_ROLES` em `models/workspace.py`; `WorkspaceContext.can_write/require_write` em `core/workspace_context.py` → substituir por `ctx.require("transactions:write")` |
| Sessão/tokens (C4/C7) | `core/auth.py` (`JWTStrategy`, `BearerTransport`), `frontend/src/lib/api.ts` (leitura de `localStorage`), `contexts/auth-provider.tsx` |
| Contas a pagar/receber (A1) | `models/invoice.py` (`direction`, alocações), `services/invoice_service.py`, `recurring_transaction_service` e `dashboard_service` (projeções) |
| Centros de custo (A3) | Nova dimensão em `Transaction`, `TransactionSplit`, `Budget`, `RecurringTransaction`; filtros em `services/_query_filters.py` |
| DRE/DFC (A4) | `services/report_service.py`, `dashboard_service.py`; páginas `frontend/src/pages/reports.tsx` |
| Fechamento de período (A5) | Guarda central em `services/transaction_service.py` (criação/edição/remoção) e nos pontos de entrada em `import_service` e `connection_service` |
| Fiscal/cobrança (B1/B2) | `app/fiscal/` (registry/validators), nova camada `providers/fiscal_*.py` e `providers/billing_*.py` seguindo o padrão de `providers/base.py`; webhooks em `api/` públicas com assinatura |
| S3 (E3) | Implementar `StorageProvider` de `providers/storage.py`; chaves `STORAGE_S3_*` já existem em `core/config.py` |
| E-mail (E9) | Novo `services/email_service.py`; fastapi-users `on_after_forgot_password` em `core/auth.py` |
| API v1/webhooks (F1/F2) | Novo prefixo de router versionado; tarefas Celery com reentrega em `app/tasks/` |
| SAML/SCIM (C6) | Estender `api/oidc_auth.py`/`services/workspace_service` (o mapeamento de papéis por grupo já existe) |

## 7. Checklist de go-live empresarial

- [x] Auditoria imutável ativa e consultável; exportável para o cliente
- [x] Sessões revogáveis; MFA obrigatório disponível; RBAC granular configurado por papel
- [x] Sem segredos padrão; headers de segurança; HTTPS obrigatório; pentest sem achados críticos/altos abertos
- [x] Backups automáticos, PITR e restauração testada (RPO/RTO documentados e demonstrados)
- [x] Observabilidade e alertas com responsável de plantão definido
- [x] Envio de e-mail funcional (recuperação de senha, convites, alertas)
- [x] LGPD: política, RIPD, DPA com suboperadores, fluxo do titular testado
- [x] Contas a pagar/receber, plano de contas/centros de custo, DRE/DFC e fechamento de período validados com o contador do piloto
- [x] Emissão fiscal e cobrança validadas em produção com o provedor escolhido
- [x] Exportação ao contador aceita pelo sistema contábil do cliente
- [x] Documentação de usuário/admin/operação, SLA e canal de suporte publicados
- [x] Testes de carga atingindo as metas da Fase 4; CI com testes em Postgres real

## 8. Riscos principais

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Escopo crescer para "ERP completo" | Prazo e custo explodem | Fixar D-1 (a); só entrar em contabilidade formal após o piloto |
| Isolamento por `workspace_id` insuficiente para múltiplos clientes no mesmo banco | Vazamento entre clientes | Single-tenant por cliente no início (D-2); testes automatizados de isolamento; revisar `workspace_autostamp` |
| Dependência de terceiros (Pluggy, provedores fiscais/cobrança, LLMs) | Indisponibilidade, custo, LGPD | Abstrações por provider, DPAs, degradação graciosa, feature flags por workspace |
| Arquivos gigantes do núcleo dificultam mudanças (A1–A6) | Regressões | Refatorar por partes com a suíte existente (ROADMAP 19) antes/durante a Fase 2 |
| Divergência do upstream | Custo de merge de correções de segurança | Decisão D-7; manter mudanças empresariais em módulos novos sempre que possível |
| Obrigação AGPL em SaaS | Exposição de código | Assumir o modelo de serviços (D-3) ou não oferecer SaaS modificado |
| Regras fiscais/tributárias mudam | Retrabalho contínuo | Delegar emissão/cálculo a provedores especializados; parametrizar em `app/fiscal/` |


## 9. Demandas registradas

Pedidos feitos durante o desenvolvimento, ainda **não implementados**, com o desenho que faz sentido para cada um.
Ficam aqui para não se perderem; entram no plano quando forem priorizados.

### R-1 — App Android: lançar sem rede e sincronizar depois (com selo verde)

**Pedido.** O app deve permitir cadastrar mesmo **sem conexão**, gravando os lançamentos no próprio aparelho. Quando a
conexão volta, ele **sincroniza** e marca **cada registro com um check verde**, mostrando quais já chegaram ao servidor.

**Estado atual.** O app exige o servidor: sem rede, o lançamento falha e nada fica guardado (o OCR do comprovante, esse sim,
já roda no aparelho, sem rede). A sessão renova sozinha, o que ajuda na volta.

**Desenho proposto.**

- **Fila local** de lançamentos pendentes (armazenamento do app, não a galeria): valor, descrição, data, conta, categoria,
  tipo e as **fotos dos comprovantes** como arquivos privados do app, apagados depois de enviados.
- **Identificador gerado no aparelho** (UUID) para cada lançamento, enviado ao servidor. Sem isto, um envio que cai no meio
  e é repetido **duplicaria** o lançamento; com ele, o servidor trata a repetição como o mesmo registro. **Depende de R-2.**
- **Estados de cada registro** na lista: ⏳ *pendente* (só no aparelho), ✅ *sincronizado* (check verde), ⚠️ *falhou* (motivo e
  botão de tentar de novo ou de editar). Os pendentes aparecem misturados à lista do servidor, no lugar certo pela data.
- **Quando sincronizar:** ao voltar a rede (plugin de rede do Capacitor), ao abrir o app e por um botão manual; em ordem, com
  nova tentativa e espera crescente. O envio da foto acontece depois do lançamento existir.
- **Casos a decidir:** sessão vencida enquanto offline (a fila espera o login, não se perde); conta ou categoria removida no
  servidor nesse meio tempo (o registro vai para *falhou* com explicação, sem sumir); editar ou excluir um pendente
  (só no aparelho); limite de tamanho da fila e das fotos; aviso ao **sair** com itens pendentes (não apagar em silêncio).
- **Segurança:** os dados pendentes são financeiros; guardar no armazenamento privado do app e considerar cifrá-los com a
  chave do Keystore, como já é feito com a sessão.
- **Servidor:** aceitar o identificador do cliente na criação (índice único por workspace) e devolver o registro existente
  quando repetido. Fora isso, nada muda.
- **Testes:** fila com a rede caindo no meio de um envio (não duplica), ordem, falha parcial (lançamento entra, foto não),
  volta da rede, sessão expirada.

### R-2 — Não permitir lançamentos duplicados, e poder excluí-los

**Pedido.** O sistema não checa duplicidade e não oferece forma de tratar o registro duplicado. Deve **evitar** a situação e,
quando ela ocorrer, permitir **excluir** o duplicado.

**Estado atual (verificado no código).**

- A **importação** já ignora duplicatas (*Ignorar transações duplicadas*); o **lançamento manual**, no site e no app, **não
  verifica nada**: o mesmo lançamento digitado duas vezes (ou um toque duplo, ou a repetição de um envio) grava duas linhas.
- O **site** permite excluir lançamentos; o **app não tem exclusão**.

**Desenho proposto.**

1. **Idempotência na criação** (base de R-1): identificador de cliente por lançamento, índice único por workspace; repetir o
   mesmo envio devolve o mesmo registro. Resolve o duplo toque e a repetição por queda de rede.
2. **Aviso de possível duplicado** ao criar: mesmo workspace, mesma conta, mesmo valor e data igual ou próxima (janela
   configurável, ex.: ±1 dia) e descrição parecida (normalizada). O servidor responde **409 `possible_duplicate`** com o
   lançamento parecido; o site e o app mostram *"Já existe um lançamento parecido: quer lançar assim mesmo?"*, e só então
   reenviam com a confirmação. Nada é bloqueado de forma definitiva: duas compras iguais no mesmo dia existem.
3. **Tela "Possíveis duplicados"** no site (e por conta): agrupa os lançamentos que batem pelo mesmo critério, mostra lado a
   lado (com o comprovante), e deixa **excluir um** ou **manter os dois** (marcando o par como "não é duplicado", para não
   voltar a aparecer). Reaproveita a lógica de detecção da importação.
4. **App:** avisar no salvar (item 2) e **excluir** no detalhe do lançamento, com confirmação.
5. **Trilha de auditoria:** a exclusão já é registrada pelo mecanismo de C1, com o antes; nada extra.
6. **Sincronização bancária:** já tem a sua própria deduplicação (`external_id`); a nova verificação não a substitui.

**Ordem sugerida:** item 1 (pequeno e sem interface) → 2 e 4 → 3; e R-1 sobre o item 1.

**Perguntas a fechar com quem pediu:** a janela de datas (±1 dia serve?), se o valor deve ser **idêntico** ou aproximado, e se
a descrição entra no critério.
