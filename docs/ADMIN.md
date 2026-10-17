# Guia do Administrador — SyncroFin Enterprise

Este guia cobre as tarefas de gestão do dia a dia para quem administra a instância:
criar e gerenciar usuários e workspaces, configurar permissões, monitorar o sistema
e responder a incidentes de segurança.

---

## 1. Primeiro acesso

Após o deploy (`docker compose up` ou Helm), acesse a URL configurada em `FRONTEND_URL`.
O primeiro usuário a completar o cadastro recebe o papel **superadmin** automaticamente.
Esse papel concede acesso ao **Painel de Administração** (menu superior direito → Administração).

> Se o auto-registro estiver desativado (`LOCAL_AUTH_ENABLED=false` ou a opção "Permitir novos
> cadastros" desligada no painel), o superadmin precisa criar cada conta manualmente antes de
> o usuário entrar.

---

## 2. Gerenciamento de usuários

### Criar um usuário

**Painel de Administração → Usuários → Convidar** (ou o endpoint `POST /api/auth/register`
quando `REGISTRATION_ENABLED=true`). Preencha nome, e-mail e papel inicial. O usuário
recebe um e-mail com um link de definição de senha.

### Resetar senha

**Painel de Administração → Usuários → (usuário) → Resetar senha**. O sistema envia um
e-mail com token de uso único. Se o SMTP não estiver configurado, o token aparece no
log do backend (`STRUCTURED_LOGGING=true`).

### Bloquear / suspender conta

**Painel de Administração → Usuários → (usuário) → Desativar**. O usuário não consegue
mais entrar; sessões ativas são invalidadas no próximo token refresh (≤ `ACCESS_TOKEN_EXPIRE_MINUTES`).

### Requisitos de segurança globais

| Variável | Padrão | O que controla |
|---|---|---|
| `REQUIRE_MFA` | `false` | Exige 2FA de todos os usuários |
| `MFA_GRACE_DAYS` | `7` | Dias de carência antes de bloquear quem não configurou 2FA |
| `PASSWORD_MIN_LENGTH` | `10` | Mínimo de caracteres em senhas novas |
| `LOGIN_MAX_ATTEMPTS` | `5` | Tentativas antes de bloquear a conta |
| `LOGIN_LOCK_MINUTES` | `15` | Duração do bloqueio (dobra a cada bloqueio, teto de 60 min) |

---

## 3. Workspaces

### Criar um workspace

**Painel de Administração → Workspaces → Criar**. Defina nome, tipo (`personal` ou
`business`) e moeda padrão. Workspaces do tipo `business` recebem o seed do plano de
contas empresarial (grupos alinhados ao SPED/DRE) automaticamente.

Para workspaces empresariais, complete o **wizard de onboarding** em
`/workspace/onboarding` para registrar razão social, CNPJ e endereço
(usados nos documentos fiscais).

### Adicionar membros

**Configurações do workspace → Membros → Convidar**. Os papéis disponíveis são:

| Papel | Pode ler | Pode escrever | Pode exportar | Pode administrar |
|---|---|---|---|---|
| Viewer (Leitor) | ✅ | ✗ | ✅ | ✗ |
| Editor | ✅ | ✅ | ✅ | ✗ |
| Owner (Dono) | ✅ | ✅ | ✅ | ✅ |

Você pode criar **papéis personalizados** em **Configurações → Papéis** para cenários
como "contador só leitura + exportação" ou "integração API somente lançamentos".

### Encerrar / arquivar workspace

**Painel de Administração → Workspaces → (workspace) → Arquivar**. O workspace fica
oculto para os membros mas preservado no banco. Para eliminar permanentemente,
use o endpoint de administração `DELETE /api/admin/workspaces/{id}` — ação irreversível.

---

## 4. Autenticação e SSO

### OIDC / SSO

Configure as variáveis `OIDC_*` no `.env` (veja `docs/CONFIGURATION.md §OIDC`).
Após reiniciar o backend, o botão **Entrar com \<OIDC_PROVIDER_NAME>** aparece na
tela de login.

Sincronização de papéis: quando `OIDC_SYNC_ROLES=true` o sistema lê a claim
`OIDC_ROLES_CLAIM` do token e eleva usuários que estejam na lista `OIDC_ADMIN_ROLES`
ao papel de administrador do workspace.

### Passkeys (WebAuthn)

Os usuários podem registrar passkeys em **Configurações da conta → Segurança →
Adicionar passkey**. Passkeys substituem senha + 2FA num único gesto biométrico ou
PIN de dispositivo. Não há configuração extra no servidor — o suporte já está
habilitado por padrão.

---

## 5. Trilha de auditoria

**Painel de Administração → Auditoria** lista todos os eventos rastreados:
criação/edição/exclusão de entidades financeiras, login, troca de papel, concessão
de token de API, etc.

- Cada evento tem: timestamp, IP do requisitante, ID do usuário, tipo de evento,
  entidade afetada, valor antes e depois (diff JSON).
- A exportação em CSV está disponível pelo botão **Exportar CSV** (aplica os filtros
  de data, workspace e tipo de evento).
- Retenção configurável: `ACCESS_LOG_RETENTION_DAYS` (padrão 183 dias); o painel
  de administração permite ajustar por instalação.

---

## 6. Backups e recuperação

### Backup manual

```bash
# Dentro do container do banco
docker compose -f docker-compose.prod.yml exec db \
  pg_dump -U postgres syncrofin_enterprise | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Backup automático e PITR (E2)

O perfil `backup` liga duas camadas, que juntas dão **RPO <= 15 min** e **RTO <= 2 h**:

| Camada | Serviço | O que faz |
|---|---|---|
| Dump diário | `db-backup` | `pg_dump` + gzip em `pgbackups`; mantém `BACKUP_KEEP_DAYS` dias |
| Base backup semanal | `db-basebackup` | `pg_basebackup` (tar+gzip, com WAL) em `pgbasebackups`; mantém `BACKUP_KEEP_BASEBACKUPS`; poda o WAL que nenhum base backup retido precisa |
| WAL contínuo | `db` (sempre ligado) | `archive_mode=on`, `archive_timeout=300`: cada segmento (ou 5 min de atividade) vai para o volume `pgwal` |

```bash
# .env
COMPOSE_PROFILES=backup
BACKUP_CRON=0 2 * * *          # dump diário às 02:00
BACKUP_KEEP_DAYS=14            # dumps mantidos
BACKUP_KEEP_BASEBACKUPS=4      # base backups mantidos (4 semanas)
BASEBACKUP_INTERVAL_DAYS=7     # intervalo entre base backups

docker compose -f docker-compose.prod.yml up -d
```

- **Primeira ativação:** `wal_level`/`archive_mode` exigem reinício do `db` (o `up -d` recria o contêiner; breve
  indisponibilidade). O primeiro base backup é feito logo ao subir; **só é possível PITR a partir dele**.
- O WAL é arquivado mesmo sem o perfil `backup`, mas só é podado por `db-basebackup`. Sem o perfil, o volume `pgwal`
  cresce sem limite: ative o perfil ou limpe-o.
- O `db-basebackup` conecta em `127.0.0.1` no namespace de rede do `db` (o `pg_hba` padrão da imagem aceita
  replicação local), sem expor replicação na rede.
- Acompanhe: `docker compose -f docker-compose.prod.yml logs db-basebackup` e
  `docker compose -f docker-compose.prod.yml run --rm db-backup ls /backups`.
- **Como as metas são atingidas:** RPO = no máximo `archive_timeout` (5 min) de WAL ainda não arquivado, mais o intervalo
  entre falha e arquivamento (folga até os 15 min); sem o volume `pgwal` íntegro, o RPO cai para o do último dump (24 h).
  Copie `pgwal`/`pgbasebackups` para fora do host (rsync/S3) — volumes no mesmo disco não protegem contra perda do disco.
  RTO = extrair o base backup + replay do WAL (medido pelo `restore_drill.sh`); o limite é 2 h.
- **Kubernetes (Helm):** `--set backup.enabled=true` cria o PVC de backups, os CronJobs de dump e de base backup e liga o
  arquivamento de WAL no StatefulSet (reinicia o PostgreSQL). Valores em `backup.*` (`charts/syncrofin/values.yaml`).
  Com PVC `ReadWriteOnce` o PostgreSQL e os CronJobs precisam estar no mesmo nó (ou use `backup.storage.accessModes: [ReadWriteMany]`).

### Teste de restauração (restore drill)

Um backup não testado não é backup. `backend/scripts/restore_drill.sh` sobe um Postgres temporário (porta aleatória em
`127.0.0.1`, sem volume persistente), restaura, valida e se remove. Os volumes de backup são montados somente-leitura;
**a produção não é tocada**.

```bash
backend/scripts/restore_drill.sh                                   # base backup mais recente + todo o WAL
backend/scripts/restore_drill.sh --target-time "2026-10-14 09:30:00+00"   # PITR até esse instante
backend/scripts/restore_drill.sh --mode dump                       # testa só o dump diário
```

Verificações: `alembic_version` com exatamente 1 linha, `users` e `workspaces` com dados e
`scripts/check_migration_chain.py`. Ao final informa o **tempo decorrido** (estimativa de RTO) e a **última transação
recuperada** (estimativa de RPO). Sai com código diferente de zero em qualquer falha ou se o tempo passar de
`RTO_LIMIT_S` (7200 s). Rode **ao menos uma vez por mês** e após mudar a versão do Postgres; agende no cron do host.
Volumes com nomes diferentes: `--base-volume`, `--wal-volume`, `--dump-volume` (ou `--base-dir` etc. para pastas).

### Restaurar em produção

```bash
# A partir de um dump
docker compose -f docker-compose.prod.yml exec -T db   psql -U postgres syncrofin_enterprise < backup_20260101.sql
```

Para PITR real: pare a stack, rode o drill com `--keep` para confirmar o ponto alvo, e então monte um `PGDATA` novo a
partir do base backup com `recovery.signal` + `restore_command='cp /wal_archive/%f %p'` e `recovery_target_time`
(mesma receita que o script aplica). Em seguida suba o `db` com esse volume.

---

## 7. Monitoramento

| Endpoint | Uso |
|---|---|
| `GET /api/health` | Liveness probe — sempre 200 se o processo está vivo |
| `GET /api/ready` | Readiness probe — verifica banco e Redis; retorna 503 se algum falhar |

Configure seu balanceador / orquestrador para rotear tráfego apenas para
instâncias que respondam 200 em `/api/ready`.

### Logs estruturados

Com `STRUCTURED_LOGGING=true`, cada linha de log é um JSON com `ts`, `level`,
`logger`, `message` e `request_id`. Direcione para Loki, CloudWatch ou qualquer
agregador compatível com JSON:

```
{"ts":"2026-10-06T12:00:00.000Z","level":"INFO","logger":"app.api.auth","message":"login ok","request_id":"abc123"}
```

---

## 8. Solicitações de titulares (LGPD)

**Painel de Administração → Requisições de dados** lista as solicitações em aberto
(acesso, portabilidade, correção e eliminação). O prazo legal é 15 dias úteis;
o painel mostra o `due_at` de cada pedido.

- **Acesso / portabilidade**: o sistema gera automaticamente um pacote de download
  com todos os dados do titular. Marque como resolvido após confirmar o envio.
- **Eliminação**: o sistema executa a deleção em cascata após re-autenticação do
  titular. Um titular dono de um workspace compartilhado não pode se eliminar enquanto
  houver outros membros — o painel indica isso.
- **Correção**: se for auto-atendível (ex.: corrigir nome de usuário), o sistema
  mostra o link direto ao titular. Caso contrário, um operador pode fazer a correção
  e registrar a resolução.

---

## 9. Atualizações

```bash
# 1. Baixar novas imagens
docker compose -f docker-compose.prod.yml pull

# 2. Parar e subir novamente (migrações rodam no startup do backend)
docker compose -f docker-compose.prod.yml up -d

# 3. Verificar
docker compose -f docker-compose.prod.yml logs backend --tail=50
```

> As migrações são automáticas (`alembic upgrade head` no entrypoint do backend).
> Nunca pule versões intermediárias — cada release inclui apenas as migrações
> acumuladas; pular pode corromper dados.

Para o Helm:

```bash
helm upgrade syncrofin oci://ghcr.io/gustavoflandal/charts-enterprise/syncrofin \
  --version <nova-versão> --reuse-values
```

---

## 10. Referência rápida

| Operação | Onde |
|---|---|
| Criar/desativar usuário | Painel Admin → Usuários |
| Criar workspace / onboarding empresa | Painel Admin → Workspaces ou `/workspace/onboarding` |
| Papéis e permissões | Workspace → Configurações → Papéis |
| Auditoria | Painel Admin → Auditoria |
| Backup automático | `COMPOSE_PROFILES=backup` no `.env` |
| Logs JSON | `STRUCTURED_LOGGING=true` no `.env` |
| Dados pessoais (LGPD) | Painel Admin → Requisições de dados |
| Provedores bancários | Workspace → Configurações → Conexões bancárias |
| Provedor NF-e | Workspace → Configurações → Emissão de NF-e |
| Variáveis de ambiente | `docs/CONFIGURATION.md` |
| Deploy e atualização | `docs/DEPLOYMENT.md` |
