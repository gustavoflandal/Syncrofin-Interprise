# Funcionalidades próprias do SyncroFin

Recursos adicionados pelo SyncroFin sobre a base herdada (itens P3 do [ROADMAP](ROADMAP.md) e a
decisão D-1 do [plano empresarial](ENTERPRISE.md)). Cada um tem regras explícitas, limites
declarados e testes.

| # | Recurso | Onde está |
|---|---------|-----------|
| 1 | [Pacote para o contador](#1-pacote-para-o-contador) | Menu do usuário → *Exportar para o contador* |
| 2 | [Saúde financeira e previsão de caixa](#2-saúde-financeira-e-previsão-de-caixa) | Painel (dashboard) |
| 3 | [Notificações](#3-notificações) | Sino na barra lateral |
| 4 | [Conciliação automática](#4-conciliação-automática) | Configurações do workspace |
| 5 | [App instalável (PWA)](#5-app-instalável-pwa) | Navegador → *Instalar aplicativo* |
| 6 | [Verificação de traduções](#6-verificação-de-traduções) | `npm run i18n:check` |
| 7 | [Recuperação de senha e convites por e-mail](#7-recuperação-de-senha-e-convites-por-e-mail) | Login → *Esqueceu a senha?*; Workspace → Membros |
| 8 | [Manual e ajuda em cada tela](#8-manual-e-ajuda-em-cada-tela) | Botão **?** no canto de toda tela; `/help` |
| 9 | [Trilha de auditoria](#9-trilha-de-auditoria) | Workspace → Configurações → Auditoria |
| 10 | [Sessões seguras](#10-sessões-seguras) | Menu da conta → Sessões e dispositivos |
| 11 | [2FA obrigatório](#11-verificação-em-duas-etapas-obrigatória) | Administração → Verificação em duas etapas |
| 12 | [Papéis e permissões](#12-papéis-e-permissões-rbac) | Workspace → Configurações → Papéis e permissões |
| 13 | [Tokens de API](#13-tokens-de-api) | Workspace → Configurações → Tokens de API |
| 14 | [Senhas e bloqueio de conta](#14-senhas-e-bloqueio-de-conta) | Login; Administração → Usuários |
| 15 | [Registros de acesso](#15-registros-de-acesso) | Administração → Registros de acesso; Menu da conta → Sessões e dispositivos |
| 20 | [Alta disponibilidade e operação](#20-alta-disponibilidade-e-operação) | Helm chart, Compose, backend |
| 21 | [Retenção de dados](#21-retenção-de-dados) | Configurações do workspace |
| 24 | [Rateio e provisões](#24-rateio-e-provisões) | Transação → *Rateio*; menu *Provisões* |
| 22 | [SAML 2.0 e SCIM](#22-saml-20-e-scim) | Login SAML; `/api/scim/v2/Users` |

> **Posicionamento (decisão D-1a):** o SyncroFin é gestão financeira e tesouraria com exportação para
> a contabilidade — **não** é um sistema contábil de partidas dobradas. O contador continua sendo > quem escritura; o SyncroFin entrega a matéria-prima limpa.

---

## 1. Pacote para o contador

`GET|POST /api/export/accountant` · `services/accountant_export_service.py` ·
`components/accountant-export-dialog.tsx`

Um `.zip` com CSVs que abrem direto no Excel/LibreOffice em português, sem assistente de importação:

| Arquivo | Conteúdo |
|---------|----------|
| `lancamentos.csv` | Movimentos efetivados no período: data, data efetiva (caixa), conta, descrição, favorecido, categoria, grupo, tipo, valor com sinal, moeda, valor na moeda principal, observações, ID |
| `resumo_por_categoria.csv` | Receitas × despesas por categoria |
| `resumo_mensal.csv` | Receitas, despesas e resultado por mês |
| `plano_de_contas.csv` | Grupos e categorias |
| `contas.csv` | Contas e saldo **atual** |
| `titulos.csv` | Faturas emitidas no período (a receber e a pagar): número, competência, vencimento, quitado, saldo, situação, dias de atraso |
| `LEIA-ME.txt` | Explica cada arquivo e os critérios |

**Convenções:** separador `;`, decimal com vírgula, datas `dd/mm/aaaa`, UTF-8 com BOM, valor com sinal
(receita positiva, despesa negativa).

**Regras que importam:**

- Só entram movimentos `posted` e não ignorados; categorias marcadas como *ignorar* ficam de fora.
- **Transferências entre contas próprias e saldos iniciais não entram** nos resumos (não são receita
  nem despesa); aparecem no `lancamentos.csv` com o tipo "Transferência" / "Saldo inicial".
- Os resumos só somam valores expressos na moeda principal do workspace (via `amount_primary` ou moeda
  igual); o que não puder ser convertido aparece no lançamento, mas fica fora do resumo.
- **Injeção de fórmulas neutralizada:** textos que começam com `=`, `+`, `-` ou `@` (uma descrição
  vinda de extrato bancário é texto controlado por terceiros) recebem um apóstrofo antes de ir para o CSV.
- Senha opcional (≥ 8 caracteres) gera zip **AES-256**; a senha viaja no corpo de um POST, nunca na URL.
- Qualquer membro pode exportar, inclusive `viewer`: convide o contador como *viewer*.
- Período máximo: 10 anos.

## 2. Saúde financeira e previsão de caixa

`GET /api/dashboard/financial-health` · `GET /api/dashboard/cash-flow-forecast?days=14..365` ·
`services/health_service.py` · `components/financial-health-card.tsx`

**Nota (0–100)** — média ponderada de três componentes, cada um uma razão simples com meta declarada:

| Componente | Cálculo | Meta | Peso |
|-----------|---------|------|------|
| Taxa de poupança | (receitas − despesas) ÷ receitas | 20 % | 40 |
| Reserva de emergência | saldo líquido ÷ despesa mensal média | 6 meses | 40 |
| Orçamentos em dia | % das categorias com orçamento dentro do limite | 100 % | 20 |

- Médias sobre os **3 últimos meses completos** (o mês corrente, incompleto, distorceria a razão).
- Componente sem dados (sem receita, sem orçamentos) é **omitido e os pesos renormalizados** — não
  vira zero. Sem nenhum componente, a nota é `null` ("sem nota ainda"), nunca um número inventado.
- Níveis: ≥ 75 boa forma · 50–74 atenção · < 50 risco.
- Saldo líquido = contas correntes, poupança e carteira, abertas. **Cartão de crédito não é liquidez.**
  "Saldo" segue a regra do painel (`_account_balance_at`): em conta **manual** é a soma das transações (a
  coluna `accounts.balance` não é mantida atualizada), em conta **conectada** é o valor do provedor.
  Conta em outra moeda só entra com o saldo convertido registrado.
- Mostra também recebíveis vencidos (faturas a receber em aberto e vencidas).

**Previsão de caixa** — parte do saldo líquido de hoje e soma **apenas o que já está prometido**:
recorrências e faturas em aberto (a receber +, a pagar −). Agrupa por semana e informa saldo mínimo,
semana do mínimo e a primeira semana negativa. Recebíveis vencidos contam como devidos hoje.
**Não** prevê gasto do dia a dia, faturas de cartão nem faturas em moeda estrangeira — o cartão diz isso
na tela. É uma projeção, não uma predição.

## 3. Notificações

`/api/notifications` · `services/notification_service.py` · `notification_delivery.py` ·
tarefa Celery `generate_notifications` (a cada hora) · `components/notification-bell.tsx`

| Tipo | Quando | Severidade |
|------|--------|-----------|
| Orçamento estourado | uso ≥ 100 % no mês | crítica |
| Orçamento perto do limite | uso ≥ 80 % | aviso |
| Fatura/conta vencendo | vence em ≤ 3 dias | aviso |
| Fatura/conta vencida | vencida (a receber = crítica; a pagar = aviso) | — |
| Falha de sincronização bancária | conexão em `error`/`expired` (só o dono da conexão) | aviso |
| Caixa projetado negativo | previsão dos próximos 30 dias fica negativa | crítica |

- **Idempotente:** cada notificação tem uma `dedupe_key` que descreve a *situação* (ex.:
  `budget:<categoria>:2026-03:over`), então rodar a cada hora não repete nada; ao mudar a situação (novo
  mês, novo vencimento) a chave muda e a pessoa é avisada de novo.
- Destinatários: `owner` e `editor` (viewers não agem sobre orçamentos/bancos). Uma linha por pessoa: ler
  a sua não some com a de outro.
- O sino consulta a contagem a cada minuto e, ao abrir, roda os geradores na hora (`POST /refresh`).
- **Canais externos (opcionais, desligados por padrão):** e-mail via SMTP e webhook. Ver
  [CONFIGURATION](CONFIGURATION.md). O envio é *best effort* e **nunca repete**: `delivered_at` é gravado
  mesmo em falha — um alerta duplicado é pior que um alerta só no sino. O webhook é assinado com
  `X-SyncroFin-Signature: sha256=<hmac do corpo>`.
- Um gerador que falha não silencia os outros.

## 4. Conciliação automática

`POST /api/reconciliation/suggestions/auto-apply` · `services/reconciliation_auto_service.py` ·
tarefa Celery `auto_apply_suggestions` (a cada hora) · `pages/workspace-settings.tsx`

O workspace (owner) define um limiar de confiança (99 % / 95 % / 90 % / 80 %, ou desligado — o padrão).
Uma sugestão pendente é aceita sozinha **somente se todas** as condições valerem:

1. a pontuação de descrição ≥ limiar (piso de 0,5, qualquer que seja a configuração);
2. o **valor é exatamente** o esperado;
3. o pagamento está a **no máximo 7 dias** da data esperada (para mais ou para menos);
4. é uma pergunta de **um** título (um pagamento oferecido contra várias faturas nunca é automático).

Cada vínculo automático usa o **mesmo caminho de escrita** do aceite manual
(`reconciliation_settle_service`), roda em um *savepoint* próprio (um que falha permanece pendente, os
demais não são desfeitos) e é registrado no histórico **sem usuário** e com `detail.auto_applied = true`.
Desfaz-se do jeito normal: desvinculando.

### 4.1 Vários pagamentos para uma fatura (N → 1)

`reconciliation_engine.evaluate_aggregate` · regra `same_client_aggregate_payments` ·
`reconciliation_suggestion_service.record_aggregate` · `reconciliation_settle_service._settle_aggregate` · migração `122`

O cliente que paga **uma fatura em parcelas** (vários Pix/depósitos). Cada depósito sozinho, no máximo, gera uma
pergunta de "pagamento parcial"; nenhum deles consegue mostrar que a **soma** é a fatura. Depois de cada lote, o
motor olha os depósitos **sem vínculo** do mesmo pagador (inclusive de sincronizações anteriores, pois as parcelas
raramente chegam juntas) e procura o menor grupo que some o valor em aberto da fatura:

- mesmo pagador, **mesma conta**, mesma moeda, dentro da janela de datas da regra (padrão: 10 dias antes da
  emissão, 60 depois do vencimento);
- até `max_transactions` depósitos por grupo (2 a 10; padrão 10) e, por segurança, no máximo 14 depósitos
  candidatos por fatura — acima disso o motor se recusa a adivinhar;
- tolerância opcional (`percent`, até 20 %, padrão 0 = soma exata); o excedente nunca é alocado além do saldo da fatura;
- um depósito nunca entra em dois grupos; se vários grupos servem (parcelas iguais), oferece-se o de datas mais
  antigas e a sugestão é marcada `ambiguous`.

**Sempre sugestão, nunca vínculo automático** (o motor não tem saída `linked` para este caso, mesmo que a regra seja
editada para "vincular", e o aceite automático por limiar ignora agregados). A sugestão é **uma linha**
(`is_aggregate = true`, depósitos em `reconciliation_suggestion_transactions`) e é aceita ou recusada **inteira**: aceitar
cria uma `InvoiceAllocation` por depósito (método = id da regra), registra um evento `accepted` por depósito e expira
as perguntas 1:1 pendentes desses mesmos depósitos. Se qualquer depósito já estiver vinculado a uma fatura, o aceite
é recusado por inteiro. Recusar é lembrado: o mesmo grupo não volta. Na fila, o grupo aparece empilhado com o valor
de cada depósito e a soma.

## 5. App instalável (PWA)

`public/manifest.webmanifest` · `public/sw.js` · `lib/register-sw.ts`

O navegador oferece *Instalar aplicativo* **só em HTTPS** (ou `localhost`); o app abre em janela própria e a casca abre
offline. Passo a passo para o usuário (Android, iPhone, computador) no manual, tópico *Usar no celular*; para o
administrador publicar com HTTPS, *Publicar com HTTPS* (e [DEPLOYMENT](DEPLOYMENT.md#https-caddy-e-app-no-celular)). O service
worker é **deliberadamente não um cache de dados**:

- `/api/*` **nunca** é interceptado nem guardado (dados financeiros não ficam no Cache Storage).
- `/static/*` (assets com hash) é *cache-first*; navegações são *network-first* com a casca como reserva.
- Registrado **só em produção**; o nginx serve `sw.js` sem cache e `manifest.webmanifest` com o tipo correto.
- Ícones `any` (192/512) e `maskable` (512, área segura de 80 %).

Limite conhecido: offline o app abre e informa que não alcança o servidor; **não há leitura offline de dados**.

## 6. Verificação de traduções

`npm run i18n:check` (`frontend/scripts/check-locales.mjs`)

O produto mantém **três idiomas: `en`, `pt-BR` e `es`**. O script compara cada idioma com `en.json` (chaves de
plural `_one/_other` contam como uma) e mostra cobertura, faltantes, extras e **"igual ao inglês"** (teto do
backlog de tradução; inclui textos legitimamente iguais, como nomes de marca). `--strict` falha se um
idioma mantido estiver fora de sincronia — e o CI roda com `--strict`. `--list <idioma>` lista as chaves.
A suíte (`i18n.test.ts`) também exige paridade de chaves e de variáveis `{{x}}`. Ver como adicionar um idioma em
[DEVELOPMENT](DEVELOPMENT.md#internacionalização-i18n).

## 7. Recuperação de senha e convites por e-mail

`services/email_service.py` · `email_templates.py` · `UserManager.on_after_forgot_password` (`core/auth.py`) ·
`api/workspaces.py` · `pages/forgot-password.tsx`, `pages/reset-password.tsx`

Antes, o endpoint `/forgot-password` gerava um token e **não o entregava a ninguém**, e não havia tela para
isso. Agora, com SMTP configurado:

- **Esqueci a senha:** o login tem o link *Esqueceu a senha?* → `/forgot-password` → e-mail com link
  `{FRONTEND_URL}/reset-password?token=…` (vale 1 hora, **uma única vez**: o token carrega a impressão digital do
  hash da senha, então trocar a senha invalida todo link pendente).
- **Convite sem senha:** o dono informa só o e-mail e o papel; a conta nasce com uma senha aleatória que ninguém
  conhece e a pessoa recebe um link (válido por 7 dias, uso único) para escolher a própria. Se o dono preferir,
  ainda pode definir a senha. Quem já tem conta é avisado de que foi adicionado.
- A resposta do convite traz `invitation_email_sent`; se o envio falhar, o convite **não é desfeito** e a interface
  avisa o dono para comunicar por conta própria.

**Salvaguardas:**

- `/forgot-password` responde **202 igual** para endereço existente ou não, e o envio é feito em *background*.
  A biblioteca só calcula um hash bcrypt (~200 ms) quando a conta existe, o que deixaria o tempo de resposta
  revelar quem tem conta; a rota própria (`api/password_reset.py`) faz um hash equivalente para endereço
  desconhecido. Na prática, medido na stack real: ~164 ms (existe) vs ~125 ms (não existe), faixas sobrepostas,
  contra 213 ms vs 19 ms antes. Não é idêntico ao milissegundo — é comparável; o limitador de taxa
  (429) cobre o restante.
- O host dos links vem de `FRONTEND_URL`, **nunca** do cabeçalho `Host` (que o cliente controla).
- Só texto simples; valores livres (nome do workspace, de quem convida) são reduzidos a uma linha antes de
  entrar no assunto, então não dá para injetar cabeçalhos (`Bcc:`).
- O token não é logado nem guardado: a página o lê uma vez e o remove da barra de endereço.
- Em instâncias só-SSO (`LOCAL_AUTH_ENABLED=false`) nada disso é enviado.
- E-mails de convite salvos em minúsculas: antes, `Ana@X.com` era gravado com a caixa original e o convite
  seguinte por `ana@x.com` não a reconhecia como usuária existente.
- Sem SMTP: a tela de recuperação diz que a instalação não envia e-mail (em vez de prometer um link) e
  convidar alguém novo continua exigindo definir a senha.
- Idiomas dos e-mails: `en`, `pt-BR`, `es` (o do destinatário; para conta nova, o de quem convida).

## 8. Manual e ajuda em cada tela

`frontend/src/help/` (`topics.ts`, `loader.ts`, `content/<idioma>/<tópico>.md`) · `components/help/` ·
`pages/help.tsx` · `scripts/build-manual.mjs` · [`MANUAL.md`](MANUAL.md)

- **Botão de ajuda em toda tela:** um botão **?** fixo no canto inferior direito (montado uma vez, em `App.tsx`,
  então nenhuma tela precisa lembrar de incluí-lo). Abre um painel lateral com a página do manual **da tela em
  que a pessoa está**; o rodapé leva ao manual completo. Atalho: `?` ou `F1` (a tecla `?` é ignorada dentro de
  campos de texto). Fecha ao trocar de tela.
- **Manual completo** em `/help` e `/help/<tópico>`: índice por seção, busca sem distinção de acentos ou
  maiúsculas (todas as palavras precisam aparecer; título pesa mais que corpo), anterior/próximo. É uma rota
  **pública**: serve para consultar antes mesmo de entrar. Não há botão de ajuda dentro do próprio manual nem no
  link público de uma cobrança (`/i/<token>`), cujo leitor não é usuário do produto.
- **Uma fonte da verdade:** `topics.ts` liga cada tópico às rotas que ele explica. `topics.test.ts` lê as rotas
  de `App.tsx` e **falha** se uma tela nova não tiver tópico (senão o botão abriria a introdução), se um caminho
  apontar para rota que não existe, se faltar a página de algum tópico, ou se um link `help:<tópico>` ou `/…`
  estiver quebrado.
- **Conteúdo:** 29 páginas em Markdown, escritas em **pt-BR** (idioma-fonte). Em `en` e `es` o painel mostra a
  página em português com um aviso — melhor que misturar idiomas em silêncio. Traduzir é criar
  `content/en/<tópico>.md`: não há mais nada a configurar.
- **`docs/MANUAL.md`** é **gerado** a partir das mesmas páginas (`npm run manual:build`, em `frontend/`); o CI roda
  `npm run manual:check` e falha se ele estiver desatualizado. Assim o manual pode ser lido no GitHub ou impresso.
- Links entre páginas usam `help:<tópico>`; o leitor os transforma em rotas do app e o gerador, em âncoras. HTML
  cru no Markdown é descartado (`skipHtml`).

---

## 9. Trilha de auditoria

`models/audit.py` · `core/audit.py` · `core/audit_context.py` · `core/request_context.py` · `api/audit.py` ·
`tasks/audit_tasks.py` · migração `093` · `pages/audit.tsx` · desenho em [FASE1](FASE1.md) (item C1)

Responde "quem fez isso, quando e de onde" para **toda criação, alteração ou exclusão** de dado financeiro ou de
configuração.

- **Gravação automática:** um *listener* do SQLAlchemy (`after_flush`) grava um evento por objeto criado, alterado
  ou excluído, **na mesma transação** da mudança (se ela desfaz, o evento também). Nenhuma rota precisa lembrar de
  chamar nada. Cada evento leva o ator (usuário, ou `system` em tarefas de fundo), IP (respeitando
  `TRUSTED_PROXY_HOPS`), navegador, código da requisição (também devolvido no cabeçalho `X-Request-Id`) e
  `{campo: [antes, depois]}`.
- **Cobertura garantida por teste:** `tests/test_audit_coverage.py` obriga que todo modelo esteja em `AUDITED` ou
  em `EXEMPT` (com motivo) em `core/audit.py`. Um modelo novo não fica de fora em silêncio.
- **Segredos nunca entram:** senha, segredo do 2FA, credenciais de banco, chaves de API e tokens aparecem como
  `***`; `raw_data` de importações é omitido. Mudanças só de saldo (que se recalcula sozinho) não geram evento.
- **Imutável no banco:** um *trigger* recusa `UPDATE`, `DELETE` e `TRUNCATE` em `audit_events`, mesmo com a
  credencial da aplicação. A tabela não tem chaves estrangeiras: o registro sobrevive à exclusão do usuário ou do
  workspace.
- **Cadeia de hashes:** cada evento é *selado* (`sha256(hash anterior + conteúdo)`) por `audit_events_seal()`,
  chamado por uma tarefa Celery a cada minuto e por toda consulta de verificação/exportação. Selar é separado de
  gravar de propósito: encadear na gravação faria todas as transações que escrevem esperarem uma trava única e
  criaria risco de *deadlock*. `GET /api/audit/verify` (administrador) confere a cadeia inteira e aponta a primeira
  linha alterada, o encadeamento quebrado ou a lacuna de numeração (linha removida). O selo mais recente é
  devolvido para ser guardado fora do servidor, o que também revela a remoção das linhas mais novas.
- **Consulta:** `GET /api/audit` (proprietário/gestor do workspace; filtros por período, ator, registro e ação),
  `GET /api/audit/export` (CSV com selo, até 100 mil linhas) e `GET /api/audit/instance` (administrador, todo o
  sistema, incluindo eventos sem workspace).
- **Limites conhecidos:** quem administra o banco pode desativar o *trigger* e reescrever a tabela: a cadeia
  detecta isso depois, não impede. A retenção/descarte (D2) ainda não existe, então a tabela só cresce; e a
  verificação lê a cadeia toda (pensada para verificações periódicas, não a cada requisição).

---

## 10. Sessões seguras

`models/user_session.py` · `services/session_service.py` · `api/sessions.py` · `core/auth.py`
(`SessionJWTStrategy`) · migração `094` · `lib/access-token.ts` · `components/sessions-dialog.tsx` ·
desenho em [FASE1](FASE1.md) (item C4)

Antes, o login devolvia um JWT de 24 h guardado no `localStorage`: qualquer script que rodasse na página podia
lê-lo, e nada o cancelava antes de vencer. Agora:

- **Token de acesso curto** (15 min), um JWT que carrega o `sid` da sessão. **Toda requisição** consulta a sessão:
  encerrá-la (sair, "encerrar aquele dispositivo", trocar a senha) vale **na requisição seguinte**, não em 15 minutos.
  Tokens antigos, sem `sid`, são recusados: cada pessoa entra de novo uma vez após a atualização.
- **Token de renovação** opaco, em cookie `httpOnly; SameSite=Strict; Path=/api/auth` (`Secure` quando
  `FRONTEND_URL` é https). O JavaScript **não consegue lê-lo**; o token de acesso vive só na **memória** da aba
  (`lib/access-token.ts`). Ao recarregar a página, o cookie é trocado por um novo token de acesso. O servidor guarda
  só o **SHA-256** do token de renovação.
- **Rotação com detecção de roubo:** cada renovação troca o token de renovação. Duas abas renovando juntas (janela de
  10 s) não são tratadas como roubo; um token antigo apresentado **depois** disso **derruba a sessão inteira**
  (`refresh_reuse`), porque não dá para saber quem é o legítimo.
- **Expiração por política:** `SESSION_IDLE_DAYS` (sem uso) e `SESSION_MAX_DAYS` (absoluta).
- **Dispositivos:** `GET /api/auth/sessions` lista as sessões ("Firefox em Windows", IP, última atividade, qual é a
  atual); `DELETE /api/auth/sessions/{id}` e `POST /api/auth/sessions/revoke-others` as encerram. Ninguém enxerga nem
  encerra sessão alheia (404).
- **O que encerra sessões sozinho:** trocar a senha (as *outras* sessões; a atual continua), redefinir a senha por
  e-mail, um administrador definir senha ou desativar a conta.
- **Todos os caminhos de login** abrem sessão: senha, 2FA, passkey, primeira execução e OIDC. No OIDC o token **não
  viaja mais na URL**: o redirecionamento leva o cookie e a página de retorno o troca por um token de acesso.
- **Auditoria:** login e encerramento de sessão entram na [trilha](#9-trilha-de-auditoria) como eventos nomeados
  (`login`, `session_revoked`), com o motivo.
- **App Android:** não usa cookie. Envia `X-Refresh-Mode: body` e guarda o token de renovação no Keystore; renova
  sozinho ao receber 401 e, ao sair, avisa o servidor. Um celular perdido pode ser encerrado por outro dispositivo.
- **Limites conhecidos:** a consulta da sessão a cada requisição custa uma leitura por chave primária (e uma escrita,
  no máximo por minuto, para "última atividade"). O bloqueio por tentativas de senha e o aviso de login em dispositivo
  novo estão na [§14](#14-senhas-e-bloqueio-de-conta). Quem tiver a `SECRET_KEY` ainda consegue assinar um token, mas ele só vale se a
  sessão que cita existir e estiver ativa.


---

## 11. Verificação em duas etapas obrigatória

`services/mfa_policy.py` · `core/auth.py` (`_enforce_mfa`) · `api/two_factor.py` (`/mfa-status`) · `api/admin.py`
(`/mfa-policy`, `/users/{id}/reset-2fa`) · migração `095` · `components/mfa-enrollment-gate.tsx`,
`mfa-reminder-banner.tsx`, `admin/mfa-policy-card.tsx` · desenho em [FASE1](FASE1.md) (item C5)

O administrador pode **exigir** o segundo fator de quem entra com a senha. O que muda em relação ao 2FA opcional de antes:

- **A regra é da instância**, guardada em `app_settings` (`mfa_required`, `mfa_required_scope` = `all`|`admins`,
  `mfa_grace_days`, e `mfa_enforced_from`, calculado ao ligar). `REQUIRE_MFA=true` no ambiente vale **na hora** e o painel não
  desfaz. Ligar e desligar entram na [trilha de auditoria](#9-trilha-de-auditoria).
- **Carência:** ao ligar, `mfa_enforced_from = agora + grace_days`. Até lá, `GET /api/auth/mfa-status` devolve
  `reminder: true` e a interface mostra uma faixa com a data. Depois, `blocked: true`.
- **O bloqueio é por sessão**, no servidor: `current_active_user` e `current_superuser` respondem **403
  `MFA_ENROLLMENT_REQUIRED`** a uma sessão sem segundo fator, exceto nas rotas de configuração (`ENROLMENT_ROUTES`: ver o
  próprio usuário, `mfa-status`, `2fa/setup`, `2fa/enable`, cadastro de passkey, lista/encerramento de sessões). Nenhuma
  decisão depende do que o cliente envia.
- **O que prova o segundo fator** (`user_sessions.mfa_verified`): entrar com código do app (`2fa`), com passkey ou pelo OIDC;
  ou, numa sessão aberta só com a senha, **terminar de configurar** o app (`2fa/enable`, que exige o primeiro código) ou
  registrar uma passkey. Assim quem foi mandado configurar entra na mesma sessão, sem sair.
- **O administrador não se tranca:** ligar a regra exige que a **própria** sessão do administrador tenha o segundo fator
  (`400 MFA_ADMIN_NOT_ENROLLED`); um administrador só de senha ficaria barrado no painel que a desliga.
- **Recuperação:** `POST /api/admin/users/{id}/reset-2fa` remove o app da pessoa e encerra as sessões (não vale para si
  mesmo); ela entra com a senha e, se a regra vale, cai na tela de configuração. Não há códigos de reserva.
- **Painel:** cartão *Verificação em duas etapas (2FA)* (liga/desliga, escopo, prazo, e quantas contas ainda não têm app) e
  um escudo verde na lista de usuários.
- **Limites conhecidos:** o segundo fator exigido é o **aplicativo autenticador** ou a **passkey**; quem só tem passkey
  precisa entrar por ela (a senha sozinha o leva à tela de configuração). Tokens de API (C7, ainda não existem) não passam
  por esta regra. Política de senhas e bloqueio por tentativas: [§14](#14-senhas-e-bloqueio-de-conta).


---

## 12. Papéis e permissões (RBAC)

`core/permissions.py` · `models/workspace_role.py` · `services/role_service.py` · `api/roles.py` ·
`core/workspace_context.py` (`require_permission`) · migração `096` · `components/roles-card.tsx` · desenho em
[FASE1](FASE1.md) (item C2)

Antes, um membro era `owner`, `editor` ou `viewer`, e o código perguntava o nome do papel. Agora o código pergunta **uma
permissão**, e um papel é um conjunto delas:

- **Catálogo fixo de 20 permissões** (`transactions.write`, `invoices.write`, `export.read`, `audit.read`,
  `members.manage`, `roles.manage`...): **uma de escrita por área** do produto, duas de saída de dados (exportar e auditoria) e três
  de administração. Acrescentar uma é acrescentar uma linha no catálogo.
- **Os papéis de sempre não mudam** e continuam em código: dono e gerente têm tudo; **editor** escreve em toda área e exporta
  (sem administrar nem auditoria); **leitor** só exporta. Uma migração não foi necessária para eles.
- **Papéis próprios, por workspace** (`workspace_roles`): nome, descrição e um subconjunto do catálogo. O membro guarda a
  **chave** do papel em `workspace_members.role` (`c_` + 8 hex), então tudo o que já lia o papel (convites, mapeamento de papéis
  do OIDC) continua funcionando. Modelos prontos: **contador**, **auditor**, **lançador** e **cobrança**.
- **Toda rota que altera dados pede uma permissão** (`Depends(require_permission(...))`, ou o portão de módulo com permissão);
  `tests/test_write_permission_coverage.py` **falha** para uma rota que não peça nenhuma. As rotas de exportação (backup, pacote do
  contador, CSV de transações) pedem `export.read`; a auditoria, `audit.read`; membros, configurações e papéis, as suas.
- **API:** `GET /api/roles` (qualquer membro), `GET /api/roles/catalog`, `POST|PATCH|DELETE /api/roles[/{id}]` (`roles.manage`).
  `GET /api/workspaces` e `/current` devolvem `permissions` do usuário, e a interface pergunta `can('export.read')`, não o nome
  do papel. Um papel em uso não é excluído; nomes são únicos e não repetem os dos papéis padrão; no máximo 30 por workspace.
- **Uma mudança no papel vale na hora** (a permissão é lida a cada requisição). Um papel que tenha uma permissão que o catálogo
  depois removeu **ignora** essa permissão, em vez de quebrar.
- Criar, alterar e excluir papéis entram na [trilha de auditoria](#9-trilha-de-auditoria).
- **Limites conhecidos:** a **leitura** dos dados não é uma permissão (todo membro lê tudo do workspace); restringir o que um membro
  **vê** exige filtrar cada consulta e relatório e não foi feito. O portão de **exportação** vale nas rotas de exportação; menus do
  site ainda mostram Backup e Pacote do contador a quem não tem `export.read` (o servidor recusa e a interface avisa). A
  **segregação de funções** (C3) e as **alçadas** (A6) usam este catálogo: o papel **Aprovador** chega com a aprovação.


---

## 12b. Segregação de funções (C3)

`models/workspace.py` (`segregation_enabled`) · `models/transaction.py` (`settled_by_user_id`, `settled_at`) ·
`services/approval_service.py` (`settle`, `check_can_settle`) · `api/approvals.py` (`POST /{id}/settle`) ·
migração `118` · workspace-settings toggle · approvals page badges

Controle opcional que, quando habilitado no workspace, impede que o mesmo ator acumule mais de uma
função no ciclo de vida de uma transação:

- **Criador != Aprovador** (já existia, A6).
- **Criador != Rejeitador** — com segregação ligada, o criador não pode rejeitar a própria
  transação; deve usar **Cancelar** (que já existia e permanece só para o criador).
- **Liquidador != Criador** e **Liquidador != Aprovador** — após a aprovação, um terceiro membro
  com permissão `approvals.approve` confirma que o pagamento foi efetuado via
  `POST /api/workspaces/{ws}/approvals/{tx}/settle`.

O endpoint grava `settled_by_user_id` e `settled_at` na transação e cria um `ApprovalEvent`
com `action="settled"`. Na fila de aprovações, badges mostram quem é Criador, Aprovador e
Liquidador; o botão **Liquidar** fica desabilitado quando o usuário logado coincide com um
dos atores anteriores.

O flag `segregation_enabled` é editável em **Configurações → Segregação de funções** (apenas
membros com `workspace.manage`). Desligado por padrão: workspaces menores não precisam dessa
formalidade.


---

## 13. Tokens de API

`models/api_token.py` · `services/api_token_service.py` · `api/api_tokens.py` · `core/auth.py` (`current_principal`) ·
`core/workspace_context.py` · migração `097` · `components/api-tokens-card.tsx` · desenho em [FASE1](FASE1.md) (item C7)

Credenciais para **programas** (integrações, scripts, o sistema do contador), no lugar de emprestar a senha de alguém.

- **Formato e guarda:** `sfn_` + 8 hex (o **prefixo**, visível) + `_` + 256 bits aleatórios. O segredo é devolvido **uma vez**, ao criar
  ou girar; o banco guarda só o **SHA-256** (`token_hash`, mascarado na auditoria) e o prefixo.
- **Um workspace e uma pessoa:** o token é do workspace em que nasceu (informar outro em `X-Workspace-Id` dá 403) e age **como quem o criou**.
- **Escopos = permissões do catálogo** ([§12](#12-papéis-e-permissões-rbac)), **sem as de administração** (`workspace.manage`,
  `members.manage`, `roles.manage`, `tokens.manage`). Só se pode dar o que se pode fazer.
- **Nunca mais que o dono, agora:** a permissão efetiva é `escopos ∩ permissões atuais do dono no workspace`. Rebaixar o dono
  encolhe os tokens dele **na hora**; tirá-lo do workspace ou desativá-lo **encerra** os tokens.
- **Sempre expira** (1 a 365 dias) e pode ser **revogada** ou **girada** (novo segredo, mesmo nome, escopos e duração; o antigo cai
  na hora). Máximo de 100 tokens ativos por workspace. `last_used_at` é atualizado no máximo uma vez por minuto.
- **Onde vale:** só nas rotas do workspace (`current_workspace`). Rotas que agem sobre a **pessoa** (`/api/users/*`, sessões,
  2FA, passkeys) ou sobre a **instalação** (`/api/admin/*`) respondem `403 API_TOKEN_NOT_ALLOWED`, e **um token não gerencia
  tokens**. O bloqueio de 2FA por sessão não se aplica a um token (não há sessão), mas criar um token exige uma sessão já verificada.
- **Auditoria:** o que um token faz é gravado com `actor_kind = api_token`, `actor_user_id` = a pessoa por trás e `detail =
  api_token:<prefixo>`.
- **API:** `GET|POST /api/api-tokens`, `POST /api/api-tokens/{id}/rotate`, `DELETE /api/api-tokens/{id}` (`tokens.manage`).
- **Limites conhecidos:** não há **limite de taxa** por token nem **restrição por IP** (o prefixo e a auditoria dizem qual token
  fez o quê). Os escopos são por área, não por recurso individual. O acesso de leitura de um token é o de todo membro (§12).


---

## 14. Senhas e bloqueio de conta

`core/password_policy.py` · `services/login_guard.py` · `api/custom_auth.py` · `api/admin.py` (`/users/{id}/unlock`) ·
`services/session_service.py` (`_is_new_device`) · `services/email_templates.py` · `app/cli.py` (`unlock-user`) · migração `098` ·
`lib/password-policy.ts` · desenho em [FASE1](FASE1.md) (item C10)

Antes, a única regra de senha morava no navegador (8 caracteres): uma chamada direta à API definia qualquer senha, e errar a senha
só era freado por um limite **por IP**, que não segura um palpite lento vindo de muitas máquinas. Agora:

- **Uma regra só, no servidor**, para todo caminho que define senha: cadastro, link de redefinição, troca pelo menu da conta, senha
  definida pelo administrador, convite e o comando `create-user`. Exige **mínimo de 10 caracteres** (`PASSWORD_MIN_LENGTH`, nunca
  abaixo de 8), no máximo 128, e recusa: senhas comuns em português e inglês (`senha123`, `Brasil2024!`: os dígitos e símbolos do fim
  são descontados na comparação), senhas que contêm o **e-mail** da pessoa e sequências óbvias (`aaaaaaaaaa`, `1234567890`,
  `qwertyuiop`). **Não** há exigência de "maiúscula + número + símbolo": ela leva a `Senha@123`, que está em toda lista.
- **O motivo é um código estável**, não uma frase (`PASSWORD_TOO_SHORT`, `_TOO_LONG`, `_TOO_COMMON`, `_HAS_EMAIL`, `_TOO_SIMPLE`),
  devolvido como `400 {"code": "INVALID_PASSWORD", "reason": …}` (no cadastro, `REGISTER_INVALID_PASSWORD`); a interface o traduz. `GET /api/info` publica
  `password_min_length` e os formulários usam o mínimo do servidor.
- **Bloqueio por conta:** `LOGIN_MAX_ATTEMPTS` (5) senhas erradas seguidas travam a conta por `LOGIN_LOCK_MINUTES` (15). A cada novo
  bloqueio a pausa **dobra**, com **teto de 1 hora**; um login correto zera tudo, e erros com mais de 24 h são esquecidos. Errar o
  código do 2FA, ou a senha ao desligar o 2FA, conta na mesma contagem.
- **Uma resposta só:** senha errada, e-mail inexistente e conta bloqueada respondem todos `LOGIN_BAD_CREDENTIALS`: a resposta não
  revela quais contas existem nem quais estão travadas. Com a conta travada a senha ainda é conferida (e ignorada), para o tempo de
  resposta também não denunciar. A pessoa é avisada **por e-mail**, com o caminho de *Esqueci a senha*.
- **Como sair do bloqueio:** esperar; **redefinir a senha por e-mail**; o administrador clicar em *Desbloquear* na lista de
  usuários (`POST /api/admin/users/{id}/unlock`, marca *Bloqueada* ao lado do nome); ou `python -m app.cli unlock-user <e-mail>`
  no servidor. Definir a senha de alguém como administrador também destrava.
- **Aviso de login em dispositivo novo:** se a pessoa já entrou antes, mas nunca deste **navegador + sistema** (o mesmo rótulo da lista
  de dispositivos, §10), recebe um e-mail com dispositivo, IP e hora, e o caminho para encerrar sessões. O primeiro login da conta não
  avisa, e falha no envio nunca impede o login.
- **Auditoria:** `login_failed` (com o motivo: `bad_password`, `bad_2fa_code`, `inactive`, `unknown_user`), `login_blocked`,
  `account_locked` e `account_unlocked` entram na [trilha](#9-trilha-de-auditoria), com IP e navegador do pedido. O e-mail digitado
  num login que falhou **não é gravado** (muitas vezes é uma senha digitada no campo errado, e a trilha não se corrige depois).
- **Contadores sem corrida:** os contadores são atualizados por `UPDATE` direto no banco, não pelo ORM: dois palpites simultâneos
  contam os dois, e cada tentativa não vira um evento de "alteração de linha" na auditoria.
- **Limites conhecidos:** quem souber o e-mail de alguém consegue **travar** a conta dela (é o preço de qualquer bloqueio por conta;
  o teto de 1 h, o e-mail, a redefinição e o desbloqueio pelo administrador limitam o dano). A detecção de dispositivo novo usa só
  navegador e sistema, não é uma impressão digital. `PATCH /api/users/me` ainda troca senha e e-mail **sem pedir a senha atual**
  (preexistente; virou item de backlog). O registro de acessos como relatório próprio foi entregue no D3 ([§15](#15-registros-de-acesso)).


---

## 15. Registros de acesso

`core/access_log.py` · `services/access_log_service.py` · `api/access_log.py` · `tasks/audit_tasks.py` (`purge_access_log`) ·
`models/audit.py` · migração `099` · `pages/admin/access-log.tsx`, `components/admin/access-retention-card.tsx`,
`components/sessions-dialog.tsx` · desenho em [FASE1](FASE1.md) (item D3) e
[o spec](superpowers/specs/2026-09-21-registros-de-acesso-design.md)

Quem entrou, quem tentou e não conseguiu, de onde, e por quanto tempo isso fica guardado. Os registros são eventos da
[trilha de auditoria](#9-trilha-de-auditoria) (append-only, com cadeia de hashes); o D3 dá a eles consulta própria, um evento que
faltava e um prazo de guarda.

- **O que é um acesso:** `login`, `login_failed` (senha errada, código de 2FA errado, conta desativada, e-mail desconhecido),
  `login_blocked`, `account_locked`, `account_unlocked`, `session_revoked` (sair, encerrar em outro dispositivo, trocar a senha) e
  `token_access`. Cada um traz data e hora (do banco, em UTC), IP e navegador da requisição.
- **Uso de token de API (`token_access`):** um token não tem login, então o acesso é registrado quando ele autentica: **um evento por
  token e por IP a cada hora** (chave no Redis com validade de 1 h). O primeiro uso e um IP novo aparecem na hora. Token inválido,
  expirado ou revogado **não** gera evento, para a trilha não ser enchida por quem não tem credencial. Se o Redis falhar, o evento é
  gravado mesmo assim, e a requisição nunca falha por causa do registro.
- **Para o administrador:** *Administração → Registros de acesso* (`GET /api/admin/access-log`) lista com filtros (período, pessoa,
  IP, tipo de evento) e exporta CSV com os hashes (`/export`). Só o administrador da instância; token de API não acessa. Consultar não
  grava evento.
- **Para cada pessoa:** em *Sessões e dispositivos*, a seção **Últimos acessos** (`GET /api/auth/access-history`) mostra os 20 acessos
  mais recentes da própria conta, incluindo falhas de login: é como alguém percebe que tentaram entrar. A pessoa vem da sessão, nunca
  do pedido: não há como ver o acesso de outra.
- **Prazo de guarda:** o parâmetro `access_log_retention_days` (Administração, cartão *Prazo de guarda dos registros de acesso*;
  `GET|PUT /api/admin/access-log/retention`) vai de **183 a 3650 dias**, com padrão 183 (o mínimo do Marco Civil, art. 15, é de 6
  meses). Sem valor salvo, vale `ACCESS_LOG_RETENTION_DAYS`. Mudar o prazo entra na trilha como qualquer parâmetro.
- **Depois do prazo, anonimização:** uma tarefa diária, às 03:30 UTC (00:30 em São Paulo; o Celery roda em `timezone="UTC"`; agendamento `crontab` do Celery beat; `purge_access_log`), zera pessoa, IP, navegador, identificador da requisição,
  detalhe e a entidade dos eventos de acesso vencidos e marca `purged_at`. A linha **fica**, com data, tipo de evento e hashes, para a
  cadeia continuar verificável. Cada execução que anonimiza algo grava `access_log_purged` (quantos, e com que prazo). Consulta e histórico não mostram
  linhas anonimizadas.
- **Quem aparece no evento é quem agiu:** a pessoa mostrada é a que **executou** a ação. Por isso um `account_unlocked` feito por um
  administrador e um `session_revoked` causado por um administrador (por exemplo, ao desativar a conta: `account_disabled`) aparecem
  sob o **administrador**, e não sob a conta afetada, tanto na página do administrador quanto nos "Últimos acessos" dele.
- **O piso vale no banco:** o trigger que proíbe alterar a trilha ganhou uma única exceção: anonimizar evento de acesso, já selado, com
  **mais de 183 dias**, mudando só essas colunas. Um erro no código, ou um prazo salvo fora da faixa, não anonimiza um evento recente.
  Nada mais na trilha mudou: `UPDATE` e `DELETE` comuns continuam recusados.
- **Integridade:** `GET /api/audit/verify` continua conferindo a sequência e o encadeamento de **todas** as linhas; nas anonimizadas
  não recalcula o conteúdo (ele deixou de existir), mas confere que continuam anonimizadas (evento de acesso com todas as colunas
  de identificação vazias e mais antigo que o piso de 183 dias; qualquer outra coisa é apontada como *purged row altered*), e nas demais confere tudo, como antes.
  **Limite conhecido:** o `verify` não recalcula o conteúdo das linhas anonimizadas; quem consegue contornar o *trigger* do banco ainda
  pode apagar o conteúdo de uma linha **antiga** da trilha reclassificando-a como evento de acesso anonimizado (a verificação pega linhas
  recentes, linhas com dado pessoal sobrando e qualquer mudança na cadeia). Fechar isso exigiria guardar um resumo (*digest*) do conteúdo
  no momento da anonimização (trabalho futuro).
- **Numa instância que já existia:** eventos de acesso com mais de 183 dias são anonimizados na primeira execução da tarefa, salvo se o
  administrador aumentar o prazo antes.
- **Limites conhecidos:** anonimizar não apaga a linha (sobram data, tipo e hashes, sem pessoa nem IP); o descarte dos demais eventos da
  trilha (mudanças de dados) não existe ainda (D2). O registro cobre o lado técnico do Marco Civil; se a sua instância se enquadra no art.
  15 é uma decisão jurídica de quem a opera. Não há alerta de IP incomum nem geolocalização.

## 16. Plano de contas, centros de custo, fechamento de período e aprovações

### Plano de contas hierárquico (A2)

`models/category.py` · `services/category_service.py` · `api/categories.py` · `pages/categories.tsx`

As categorias passam a ser **hierárquicas**: uma categoria pode ter categorias filhas, com profundidade ilimitada.
Cada categoria tem um **código contábil** opcional e uma **natureza** (receita, despesa, custo) herdada do grupo.
O editor no frontend apresenta a árvore em cascata e o seletor ao categorizar uma transação mostra a hierarquia
completa com busca por nome ou código.

### Centros de custo (A3)

`models/cost_center.py` · `services/cost_center_service.py` · `api/cost_centers.py` · `pages/cost-centers.tsx`

Dimensão de custo/projeto/departamento em lançamentos, orçamentos e recorrências. Relatórios filtram e agrupam por
centro de custo. O rateio entre centros está na [§26](#26-rateio-e-provisões).

### Fechamento de período (A5)

`models/period_close.py` · `services/period_close_service.py` · `api/period_closes.py` · `pages/workspace/periods.tsx`

O administrador pode fechar (e reabrir) meses de um workspace. Um período fechado bloqueia criação, edição e remoção
de transações, importações e sincronizações bancárias naquele intervalo. A reabertura é auditada. A UI fica em
**Configurações → Períodos**.

### Aprovações por alçada (A6)

`models/approval.py` · `services/approval_service.py` · `api/approvals.py` · `pages/workspace/approvals.tsx`

Regras de alçada por valor e/ou categoria: transações acima do limite exigem aprovação de alguém diferente do criador.
A fila de revisão mostra pendências, e a aprovação/rejeição é registrada na trilha de auditoria. A segregação de
funções (C3) complementa: criador ≠ aprovador ≠ liquidador.

---

## 17. Relatórios com identidade da empresa e exportação PDF/XLSX

`pages/reports.tsx` · `pages/workspace-settings.tsx` · `lib/api.ts` (`reports.downloadFile`, `workspaces.uploadLogo/deleteLogo`) ·
`schemas/workspace.py` (`logo_storage_key`) · Enterprise G2

A página de relatórios (Patrimônio Líquido e Receitas/Despesas) oferece botões de exportação **PDF** e **XLSX**
visíveis apenas para usuários com a permissão `export.read`. Os relatórios exportados incluem o cabeçalho com a
identidade visual da empresa (logo e nome), quando configurados.

### Logo da empresa

Na página de configurações do workspace, administradores podem enviar um logo (JPG, PNG ou WebP, até 2 MB)
que é armazenado pelo backend e servido em `/api/workspaces/{id}/logo`. O logo aparece no cabeçalho dos
relatórios PDF gerados pelo backend, reforçando a identidade corporativa.

### Perfis de tela por papel

O sistema de papéis e permissões (`core/permissions.py`, custom roles do workspace) controla quais módulos e
ações cada usuário vê. O portão `export.read` decide se os botões de exportação aparecem — um **viewer** pode
ver os gráficos, mas só um **editor** ou papel customizado com `export.read` pode baixar o PDF/XLSX.

---

## 18. Obrigações fiscais e retenções

### Obrigações fiscais

Impostos recorrentes (DAS, DARF, ISS, INSS, ICMS) são cadastrados como recorrências com tipo
de obrigação, código da receita (para DARFs) e offset de competência. Aparecem automaticamente
na previsão de caixa do AR/AP como saídas separadas ("Impostos"), e na aba Impostos da página
de recorrências com resumo mensal.

Endpoints:
- `GET /api/tax-obligations` — lista obrigações (filtro de recorrências)
- `GET /api/tax-obligations/summary` — total mensal por tipo

### Retenções na fatura

Faturas a receber podem ter retenções (IRRF, ISS, PIS, COFINS, CSLL, INSS) que reduzem o valor
efetivamente recebido sem alterar o saldo devedor. `net_receivable = total − total_withheld`.

- O forecast AR/AP projeta o valor líquido para faturas com retenção.
- A conciliação reconhece pagamentos com valor menor quando a diferença corresponde a uma
  alíquota de retenção conhecida (estratégia `same_client_net_of_withholding`).

Endpoints:
- `POST /api/invoices/{id}/withholdings` — adiciona retenção
- `PATCH /api/invoices/{id}/withholdings/{wid}` — edita retenção
- `DELETE /api/invoices/{id}/withholdings/{wid}` — remove retenção
- Inline em `POST /PATCH /api/invoices/{id}` via campo `withholdings`

---

## 19. Retenção documental fiscal

Documentos fiscais anexados a faturas podem ser travados para cumprir os prazos de guarda
obrigatórios (mínimo 5 anos, conforme legislação tributária brasileira). Uma vez travado, o
anexo se torna imutável: não pode ser alterado nem excluído até que o prazo de retenção expire.

Campos no `InvoiceAttachment`:
- `is_locked` — indica se o anexo está travado.
- `locked_at` — data/hora em que o bloqueio foi aplicado.
- `locked_by` — identificador do usuário que aplicou o bloqueio.
- `retention_until` — data em que o prazo de retenção expira (padrão: 5 anos a partir do
  bloqueio).

Comportamento:
- `POST /api/invoices/{id}/attachments/{aid}/lock` trava o anexo e define `retention_until`
  (padrão 5 anos).
- `DELETE` e `PATCH` em anexos travados retornam **403 Forbidden**.
- No frontend, anexos travados exibem ícone de cadeado, badge com a data de retenção, e os
  botões de excluir e editar ficam ocultos. Anexos do tipo `fiscal` que ainda não estão travados
  mostram um botão de escudo para travar.

Endpoint:
- `POST /api/invoices/{id}/attachments/{aid}/lock` — trava o anexo para retenção fiscal

---

## 20. Alta disponibilidade e operação

`core/database.py` (pool tuning) · `alembic/env.py` (advisory lock) · `worker.py` (celery hardening) ·
`docker-compose.prod.yml` · `charts/syncrofin/` · desenho em [ENTERPRISE](ENTERPRISE.md) (E4, E8, E11)

### E4 — Alta disponibilidade

- **PodDisruptionBudget (PDB):** backend, frontend e worker criam um PDB quando `replicaCount > 1`,
  garantindo que pelo menos 1 pod permanece disponivel durante drains e atualizacoes de no.
- **Rolling update sem indisponibilidade:** `maxUnavailable: 0` + `maxSurge: 1` em todos os
  Deployments (backend, frontend, worker).
- **Anti-afinidade de pod:** o backend prefere distribuir replicas por nos distintos
  (`preferredDuringSchedulingIgnoredDuringExecution`, `kubernetes.io/hostname`).
- **Readiness probe aponta para `/api/ready`** (verifica DB + Redis, retorna 503 em falha) em vez
  de `/api/health` (liveness). Kubernetes so envia trafico para pods prontos de verdade.
- **Pool de conexoes do banco:** `pool_pre_ping=True`, `pool_recycle=300`, `pool_size=10`,
  `max_overflow=20` no `create_async_engine`, evitando conexoes obsoletas e controlando o uso.
- **Redis com persistencia AOF:** `appendonly yes --appendfsync everysec` no Compose e no chart,
  com liveness/readiness probe (`redis-cli ping`) no StatefulSet.
- **Beat singleton:** `replicas: 1` fixo no Deployment do beat (comentario no template);
  `--pidfile=` no Compose para evitar PID obsoleto em containers efemeros;
  `beat_schedule_filename` em `/tmp` para funcionar em filesystem read-only.

### E8 — Migracoes sem indisponibilidade

- **Advisory lock no Alembic:** `pg_advisory_lock(42)` antes de rodar migracoes, liberado depois.
  Impede que dois pods (ou o Job + um pod reiniciando) executem migracoes simultaneamente.
- **Timeouts de seguranca:** `lock_timeout = 30s` e `statement_timeout = 300s` no env.py, para
  que uma migracao travada nao segure o lock para sempre.
- **Servico separado no Compose:** `db-migrate` roda `alembic upgrade head` uma unica vez e o
  backend so inicia apos `service_completed_successfully`. No Helm, o Job de migracao ja existia
  (`job-migration.yaml`, hook post-install/post-upgrade).

### E11 — Fila de trabalhos idempotente

- **Acknowledge tardio:** `task_acks_late=True` + `task_reject_on_worker_lost=True` — se o
  worker morre no meio de uma task, o broker reenvia para outro.
- **Prefetch controlado:** `worker_prefetch_multiplier=1` evita que um worker reserve tarefas
  que nao consegue processar a tempo.
- **Rastreamento de estado:** `task_track_started=True` e `result_expires=86400` (24 h).
- **Retentativas com backoff:** `sync_all_connections` e `sync_single_connection` (3 tentativas,
  backoff exponencial, max 600 s); `generate_all_recurring` e `generate_notifications` (2
  tentativas, backoff).
- **Nota:** as tarefas ja sao idempotentes por desenho (conferem `last_sync_at`, `next_occurrence`,
  etc.). As retentativas apenas automatizam o que antes precisaria de intervencao manual.

### E5 — Observabilidade: métricas e tracing

`core/metrics.py` · `core/tracing.py` · `core/logging_config.py` · `api/observability.py` ·
`charts/syncrofin/templates/backend/servicemonitor.yaml`

- **Métricas:** `GET /api/metrics` (formato Prometheus) com `http_requests_total` e
  `http_request_duration_seconds`. No Kubernetes, `metrics.serviceMonitor.enabled=true` cria o
  `ServiceMonitor` (Prometheus Operator); `interval` e `labels` são configuráveis.
- **Tracing (opcional):** defina `OTEL_EXPORTER_OTLP_ENDPOINT` (ex.: `http://otel-collector:4317`) e o
  backend instrumenta as rotas FastAPI e as queries SQLAlchemy, exportando via OTLP. Sem a variável,
  nada é carregado. `OTEL_EXPORTER_OTLP_PROTOCOL=grpc` (padrão) ou `http`; `OTEL_SERVICE_NAME`
  (padrão `syncrofin-backend`). `/api/health`, `/api/ready` e `/api/metrics` não geram spans.
- **Correlação:** com `LOG_FORMAT=json`, cada linha de log dentro de um span inclui `trace_id` e
  `span_id`, para saltar do log para o trace.

## 21. Retenção de dados

`GET|PATCH /api/data-retention/` · `POST /api/data-retention/purge` ·
`services/data_retention_service.py` · Configurações do workspace

Política de retenção de dados configurável por workspace, com anonimização ou exclusão automática de dados expirados:

| Tipo de dado | Padrão | Mínimo | O que acontece |
|---|---|---|---|
| Transações | 2555 dias (~7 anos, exigência fiscal brasileira) | 365 dias | Anonimização (descrição → `[anonimizado]`, notas e favorecido removidos, valor/data/categoria preservados) ou exclusão |
| Anexos | 1825 dias (~5 anos) | 365 dias | Remoção do blob de armazenamento + registro do banco |
| Auditoria | 3650 dias (~10 anos) | 365 dias | Registros de acesso anonimizados pela tarefa separada `purge_access_log`; eventos gerais são imutáveis por design |

### Regras

- Cada workspace tem uma política própria (`data_retention_policies`, migração 119).
- Os prazos mínimos são aplicados por CHECK constraints no banco (≥ 365 dias).
- **Anonimizar ao expirar** (padrão): preserva totais contábeis ao substituir dados pessoais.
- **Purga automática**: tarefa Celery diária às 02:00 UTC (`purge-expired-data`).
- **Purga manual**: botão nas configurações do workspace (requer permissão `workspace.manage`).
- Anexos com `retention_until` futuro ou `is_locked=true` (retenção documental fiscal) são preservados.
- Eventos de auditoria são imutáveis (append-only com hash chain SHA-256); a anonimização de registros de acesso já é tratada pela tarefa `purge_access_log` existente.

---

## 22. SAML 2.0 e SCIM

`api/saml_auth.py` · `api/scim.py` · migração 120

### SAML 2.0 — Service Provider

Autenticação federada via SAML 2.0 para IdPs empresariais (Azure AD, Okta, OneLogin,
Keycloak etc.):

| Endpoint | Descrição |
|----------|-----------|
| `GET /api/auth/saml/config` | Retorna status habilitado, nome do provedor e se auth local está ligado |
| `GET /api/auth/saml/metadata` | XML de metadados do SP para registrar no IdP |
| `GET /api/auth/saml/login` | Redireciona ao SSO URL do IdP |
| `POST /api/auth/saml/acs` | Assertion Consumer Service — recebe e valida a resposta SAML |
| `GET /api/auth/saml/slo` | Single Logout — redireciona ao logout do IdP |

- Fluxo de login espelha o OIDC: redirect → IdP → ACS → sessão httpOnly → frontend.
- Lookup por `(saml_idp_entity_id, saml_name_id)`, fallback por e-mail, auto-registro.
- Sincronização de papéis por atributo SAML (`SAML_SYNC_ROLES`, `SAML_ROLES_ATTRIBUTE`).
- python3-saml (`onelogin.saml2`) processa XML; requer `xmlsec1` no sistema.
- Sessão SAML conta como MFA verificado (`VERIFIED_METHODS` em `mfa_policy.py`).

### SCIM 2.0 — Provisionamento de Usuários

Provisionamento server-to-server (RFC 7644) com autenticação por bearer token dedicado:

| Endpoint | Descrição |
|----------|-----------|
| `GET /api/scim/v2/Users` | Lista usuários; aceita filtro `userName eq "email"` |
| `GET /api/scim/v2/Users/{id}` | Retorna um usuário em formato SCIM |
| `POST /api/scim/v2/Users` | Cria usuário; idempotente por `externalId` |
| `PUT /api/scim/v2/Users/{id}` | Substituição completa (nome, active, externalId) |
| `PATCH /api/scim/v2/Users/{id}` | Atualização parcial (PatchOp); usado para desativação |
| `DELETE /api/scim/v2/Users/{id}` | Desativa o usuário (soft-delete; não apaga) |

- Autenticação por `SCIM_BEARER_TOKEN` — fora do sistema de sessões/JWT.
- Usuário criado recebe workspace pessoal, carteira, categorias e regras padrão.
- `SCIM_DEFAULT_WORKSPACE_ID` adiciona o usuário a um workspace compartilhado.
- `scim_default_role` no workspace define o papel padrão (editor por padrão).

### Configuração

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `SAML_ENABLED` | `false` | Liga/desliga SAML SSO |
| `SAML_PROVIDER_NAME` | `SAML` | Nome exibido no botão de login |
| `SAML_IDP_METADATA_URL` | — | URL dos metadados do IdP |
| `SAML_SP_ENTITY_ID` | — | Entity ID do SP (derivado automaticamente se vazio) |
| `SAML_SP_CERT` / `SAML_SP_KEY` | — | Certificado e chave PEM do SP (opcional) |
| `SAML_SYNC_ROLES` | `false` | Sincroniza papéis a partir de atributo SAML |
| `SCIM_ENABLED` | `false` | Liga/desliga provisionamento SCIM |
| `SCIM_BEARER_TOKEN` | — | Token de autenticação para o endpoint SCIM |
| `SCIM_DEFAULT_WORKSPACE_ID` | — | Workspace ao qual novos usuários SCIM são adicionados |

## 23. Proteção de upload e CORS configurável

Todo upload passa por `backend/app/core/upload_guard.py` (`validate_upload`):

- **Leitura em pedaços** (1 MB) com teto por categoria; ao estourar, `413` sem carregar o arquivo inteiro.
- **Allowlist de extensão** e conferência dos **magic bytes** contra a extensão (JPEG, PNG, GIF, WebP, HEIC, PDF, ZIP/XLSX; texto puro sem bytes nulos nem assinatura binária; XML precisa começar por `<`). Divergência (ex.: `.png` com conteúdo JPEG) → `422`.
- **SVG e HTML sempre recusados**, inclusive com extensão trocada (marcadores `<svg`, `<html`, `<script`… no início do conteúdo), por serem vetor de XSS.
- Devolve `(bytes, content_type detectado)`; o tipo gravado é o detectado, não o que o cliente declarou.

| Categoria | Limite | Extensões |
|---|---|---|
| `attachment` | `STORAGE_MAX_FILE_SIZE_MB` | `STORAGE_ALLOWED_EXTENSIONS` |
| `import` | 50 MB | csv, ofx, qfx, qif, xml (+ txt, ret, rem, cnab para CNAB) |
| `logo` | 2 MB | jpg, jpeg, png, webp |
| `knowledge` | 20 MB | pdf, txt, md, csv |

Aplicado em anexos de transação e de título, logos (workspace e fatura), importações (extrato, NF-e, AR/AP, favorecidos, categorias, ativos) e base de conhecimento dos agentes. No download, `Content-Disposition: inline` só para imagem/PDF (demais `attachment`) e sempre `X-Content-Type-Options: nosniff`.

**nginx:** `client_max_body_size ${UPLOAD_MAX_BODY_SIZE}` em `/api/` (padrão `50m`).

**CORS:** `CORS_ORIGINS` (lista separada por vírgula). Vazio → apenas `FRONTEND_URL`. `*` é ignorado, pois as chamadas usam credenciais.

Mensagens de erro de UI: `upload.tooLarge` e `upload.invalidType` (en, pt-BR, es).

## 24. Backup e recuperação em ponto no tempo (PITR)

O perfil `backup` do Compose (e `backup.enabled` no Helm) protege o banco em três camadas: **dump diário**, **base
backup semanal** e **WAL arquivado continuamente** (`archive_timeout=300`). Com base backup + WAL é possível restaurar
o banco em qualquer instante após o base backup mais antigo retido, o que dá **RPO <= 15 min**; o **RTO** alvo é de
**2 h**.

`backend/scripts/restore_drill.sh` é o exercício de restauração: sobe um Postgres temporário, restaura o backup mais
recente (ou `--target-time` para PITR), confere `alembic_version`, `users`, `workspaces` e a cadeia de migrações,
informa o tempo gasto (RTO) e a última transação recuperada (RPO) e falha se algo estiver errado ou o tempo passar do
limite. Procedimento completo em [ADMIN §6](ADMIN.md#6-backups-e-recuperação).

## 25. Conectores ERP (F3)

Ligam o workspace ao ERP da empresa. Código em `backend/app/erp/` (contrato e registro), `services/erp_service.py`
(regras), `api/erp.py` (rotas `/api/erp/*`), `tasks/erp_tasks.py` (sync em segundo plano) e `pages/erp-connections.tsx`.

- **Contrato:** `ErpConnector` (Protocol) com `test_connection`, `pull_chart_of_accounts`, `pull_payees`, `push_transactions`
  e `push_invoices`, sobre dataclasses neutras (`ErpAccount`, `ErpPayee`, `ErpTransaction`, `ErpInvoice`, `SyncResult`).
  Um conector novo é um módulo que chama `register_connector("nome", Classe)`.
- **Omie** (`erp/omie.py`): JSON-RPC sobre POST (`app_key`/`app_secret` no corpo), espaçamento de ~3 req/s. Importa categorias
  (`ListarCategorias`) e clientes/fornecedores (`ListarClientes`, paginado, CPF/CNPJ); envia faturas abertas com
  `IncluirContaReceber`/`IncluirContaPagar`, usando o id da fatura como `codigo_lancamento_integracao` (reenvio vira "já existe",
  não duplica). Envio de transações avulsas não é suportado pelo Omie e é registrado como tal.
- **Conta Azul:** esqueleto registrado; `test_connection` devolve falso com "Conta Azul integration coming soon".
- **Direção fixa por entidade:** `category` e `payee` são *pull*; `transaction` e `invoice` são *push*.
- **Idempotência:** `erp_entity_mappings` liga id local a id externo por (conexão, tipo). O pull atualiza em vez de duplicar e
  reaproveita categoria/beneficiário local de mesmo nome; o push pula o que já foi enviado.
- **Credenciais** ficam cifradas em `erp_connections.credentials_enc` (Fernet, chave derivada de `SECRET_KEY`) e nunca saem pela API.
- **Execuções:** cada sync grava um `erp_sync_runs` (criados, atualizados, erros) e resume o estado em `erp_connections`.
  Erro em um item não derruba o lote; falha geral marca a execução como erro. `POST /api/erp/connections/{id}/sync` só enfileira a
  task Celery `sync_erp_connection` (resposta 202).
- **Permissões:** `erp.read` (ver conexões, histórico e mapeamentos) e `erp.manage` (criar, editar, testar e sincronizar).
- **Opções do Omie** em `sync_config`: `default_category_code` e `default_account_id`, exigidos pelo Omie em todo título enviado.

## 26. Rateio e provisões

**Rateio entre centros de custo.** Uma transação pode ser dividida entre vários centros (`cost_center_allocations`). Regra: havendo fatias, elas somam exatamente o valor da transação; sem fatias, vale `cost_center_id` (legado). Na UI: seção *Rateio* ao editar a transação (percentual ou valor, indicador de soma, última linha completa os 100%).

- `GET/PUT/DELETE /api/transactions/{id}/allocations` (permissão `transactions.write` para escrever). `PUT` aceita `percentage` **ou** `amount` por item (não misturar), valida centros do workspace e fechamento de período (A5); percentuais toleram ±0,01 e o resíduo de centavos vai na última fatia.
- `cost_center_id` passa a apontar para o centro de maior fatia (compatibilidade com filtros e orçamentos antigos). Alterar o valor da transação reescala as fatias pelos percentuais.
- DRE e DFC filtrados por centro de custo contam só a fatia daquele centro.

**Provisões e diferimentos.** Um cronograma (`accrual_schedules`) reparte `total_amount` em N meses (do mês de `start_date` ao de `end_date`), com uma parcela (`accrual_entries`) por mês e o resíduo de arredondamento na última. *Provisão* gera **débito**; *diferimento* gera **crédito** (`source="accrual"`, data = 1º do mês).

- Lançamento: tarefa Celery `post_due_accruals` no dia 1 de cada mês e botão *Lançar agora* (`POST /api/accruals/post`). Idempotente. Parcelas em período fechado ficam `skipped` e são retomadas se o período for reaberto.
- A transação lançada é real e **altera o saldo da conta**: use uma conta dedicada às provisões.
- `GET/POST /api/accruals`, `GET/DELETE /api/accruals/{id}` (cancelar encerra o que falta; o lançado permanece). Página `/accruals`.

## 27. Pagamentos PIX/TED com dupla aprovação (F4)

Ordens de pagamento iniciadas pelo SyncroFin por uma API bancária, em `/payments` (menu, junto de Títulos). A dupla aprovação **sempre** vale: não há opção para desligá-la.

**Ciclo:** `draft` → `pending_approval` → `approved` → `sent` → `confirmed` \| `failed` \| `cancelled`. Rejeitar devolve a rascunho e zera as aprovações.

**Segregação:** criador ≠ 1º aprovador ≠ 2º aprovador ≠ quem envia. O serviço impõe isso para qualquer papel, inclusive o proprietário.

**Permissões:** `payments.read` (grupo reports), `payments.write` (data: criar, editar rascunho, submeter, cancelar, consultar), `payments.approve` e `payments.send` (admin). Como ficam fora do grupo `data`, o papel `editor` padrão não aprova nem envia; só owner/manager ou um papel próprio.

**Provedor:** `app/providers/payment_provider.py` define o Protocol (`create_payment`, `get_status`, `cancel_payment`, `verify_webhook`, `parse_webhook_event`). O único adaptador é `sandbox` (confirma 5 s depois, sem estado: o `external_id` guarda o instante). Adaptadores reais entram em `payment_service.get_provider`.

**Idempotência:** `(workspace_id, idempotency_key)` é único; repetir a chave devolve a ordem existente (HTTP 201 com a mesma ordem, sem duplicar). A mesma chave vai ao provedor no envio. Transições usam `SELECT ... FOR UPDATE`.

**Confirmação:** por webhook (`POST /api/payments/webhook/{provider}/{workspace_id}`, sem sessão; o status `confirmed` do webhook é reconferido com `get_status` antes de lançar) ou pela tarefa `check_pending_payments` (a cada 5 min) / botão **Consultar status**. Ao confirmar, cria um `Transaction` de débito (conta de origem ou a primeira conta corrente) e, se houver fatura, um `InvoiceAllocation`. Sem conta, a ordem confirma sem lançamento (aviso no log).

**Trilha:** `payment_approval_events` (submit, approve, reject, send, cancel). Tabelas `payment_orders` e `payment_approval_events` (migração 122).

## 28. Acessibilidade (WCAG 2.1 AA)

- **Pular para o conteúdo:** o primeiro item focável do layout é um link (`a11y.skipToContent`) que leva ao `<main id="main-content">`.
- **Contraste:** `--primary` claro passou a `#4F46E5` (≈5,6:1 sobre branco); no tema escuro, `--primary-foreground` é escuro sobre `#818CF8` e `--muted-foreground` foi clareado para `#9CA3AF`.
- **Rótulos:** botão de menu móvel e de modo privacidade com `aria-label`; `<nav>` da barra lateral com `aria-label` (`a11y.mainNavigation`); `TableHead` emite `scope="col"` por padrão.
- **Lint:** preset `jsx-a11y/recommended` ativo como *aviso* (cerca de 70 ocorrências legadas, em especial `div` clicáveis); `control-has-associated-label` e `anchor-has-content` seguem como erro.
- **Testes:** `src/__tests__/a11y-smoke.test.tsx` roda o axe (`vitest-axe`) em botões, formulário, diálogo e tabela. Contraste não é medido no jsdom; fica a cargo dos tokens de `index.css`.
