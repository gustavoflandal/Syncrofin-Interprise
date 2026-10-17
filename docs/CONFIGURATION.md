# Configuração

Toda a configuração é feita por **variáveis de ambiente**, lidas por `backend/app/core/config.py`
(`pydantic-settings`; também aceita segredos em arquivos via `CREDENTIALS_DIRECTORY`, padrão
`/run/secrets`). Com Docker Compose, coloque-as num `.env` na raiz (modelo: `.env.example`).

> **Atenção:** o Compose só repassa ao container as variáveis listadas em `x-backend-env`
> (`docker-compose.yml` / `docker-compose.prod.yml`). Uma variável nova do `config.py` só chega ao
> backend se você também a declarar lá. Ex.: `TRUSTED_PROXY_HOPS` existe no compose de produção
> (padrão `1`), mas não no de desenvolvimento.

## Essenciais

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `SECRET_KEY` | **obrigatória** em produção | Assina os JWT (`openssl rand -hex 32`, 32+ caracteres). O backend **recusa iniciar** com o valor de exemplo, vazio ou curto, exceto com `DEBUG=true`. |
| `DEFAULT_LANGUAGE` / `DEFAULT_CURRENCY` / `DEFAULT_DATE_FORMAT` / `DEFAULT_TIMEZONE` | `pt-BR` / `BRL` / `DD/MM/YYYY` / `America/Sao_Paulo` | O que uma conta nova recebe (registro e primeira execução), incluindo o idioma das categorias e da carteira iniciais. Quem escolhe outra coisa no cadastro fica com o que escolheu. |
| `POSTGRES_PASSWORD` | **obrigatória** no compose de produção | Senha do Postgres (`openssl rand -hex 24`). O backend recusa a senha `postgres` em host que não seja `localhost`. |
| `FRONTEND_URL` | `http://localhost:${FRONTEND_PORT}` | URL pública. Usada em CORS, callbacks OAuth/OIDC e passkeys. |
| `FRONTEND_PORT` / `BACKEND_PORT` | `3100` / `8100` | Portas no host. Diferentes das da edição Community (`3000` / `8000`) para as duas poderem rodar na mesma máquina. |
| `DEBUG` | `true` (dev) | Log de SQL e modo verboso. |
| `DATABASE_URL` | definido no compose | `postgresql+asyncpg://…/syncrofin`. |
| `REDIS_URL` | definido no compose | Broker Celery, rate limit e cache. |
| `DB_IMAGE` | `pgvector/pgvector:pg16` | Imagem do Postgres (precisa da extensão `vector`). |
| `TRUSTED_PROXY_HOPS` | `0` (dev) / `1` (prod) | Nº de proxies confiáveis à frente do backend (rate limit por IP e endereço registrado na auditoria e nas sessões). |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | Validade do token de acesso. É curto de propósito: quem mantém a pessoa conectada é o cookie de renovação, que o servidor pode revogar. |
| `SESSION_IDLE_DAYS` | `7` | Uma sessão termina após esses dias **sem ser renovada** (sem uso). |
| `REQUIRE_MFA` | `false` | `true` exige o segundo fator (app autenticador ou passkey) de **todos**, **imediatamente**, e o painel não consegue desfazer. Sem isto, o administrador pode exigir pelo painel, com prazo de carência. |
| `MFA_GRACE_DAYS` | `7` | Dias entre o administrador ligar a exigência no painel e ela passar a valer; até lá, só há um aviso. |
| `SESSION_MAX_DAYS` | `30` | Uma sessão termina após esses dias desde o login, **mesmo em uso constante**. |
| `PASSWORD_MIN_LENGTH` | `10` | Tamanho mínimo de uma senha nova, aplicado no servidor a todo caminho que define senha (nunca fica abaixo de 8). Além dele, a política recusa senhas comuns, com o e-mail da pessoa e sequências óbvias. |
| `LOGIN_MAX_ATTEMPTS` | `5` | Senhas erradas seguidas (ou códigos de 2FA errados) até a conta ser travada. |
| `LOGIN_LOCK_MINUTES` | `15` | Duração do primeiro bloqueio; a cada bloqueio seguinte a pausa dobra, com teto de 1 hora. Um login correto zera a contagem. O administrador desbloqueia pelo painel ou por `python -m app.cli unlock-user <e-mail>`. |
| `ACCESS_LOG_RETENTION_DAYS` | `183` | Por quantos dias os registros de acesso (logins, falhas, bloqueios, sessões encerradas, uso de token) são guardados antes de serem **anonimizados** (pessoa, IP e navegador são removidos; a linha e os hashes ficam). Vai de 183 (o mínimo legal de 6 meses) a 3650. O administrador muda o valor em Administração; este é o que vale até ele mudar. Em instância existente, o que passar de 183 dias é anonimizado na primeira execução da tarefa diária. |
| `TESOURO_DIRETO_ENABLED` | `true` | Cotações do Tesouro Direto (CSV do Tesouro Transparente). |

O registro público de novos usuários é controlado pelo painel de administração (tabela
`app_settings`), não por variável de ambiente.

## Sincronização bancária (opcional)

Cada provider se registra sozinho quando as credenciais estão presentes.

### Pluggy — bancos brasileiros (Open Finance)

Conta em <https://pluggy.ai>. Cadastre `http://localhost:${FRONTEND_PORT}/oauth/callback` como
redirect permitido.

```
PLUGGY_CLIENT_ID=...
PLUGGY_CLIENT_SECRET=...
# PLUGGY_OAUTH_REDIRECT_URI=   (vazio = derivado de FRONTEND_URL)
```

### Enable Banking — Europa (PSD2)

Crie uma aplicação *Production* em <https://enablebanking.com>, baixe a chave PEM e salve em
`./secrets/` (ignorado pelo git).

```
ENABLE_BANKING_APP_ID=...
ENABLE_BANKING_PRIVATE_KEY_FILE=/app/secrets/enable_banking_private.pem
ENABLE_BANKING_OAUTH_REDIRECT_URI=https://seu-host/oauth/callback
```

O redirect precisa coincidir exatamente com um dos cadastrados no portal, e o EB de produção exige
HTTPS (em dev, use túnel ou o sandbox). No plano gratuito é preciso pré-vincular as contas no
portal antes de conectar.

### SimpleFIN — EUA/internacional

Sem chave de API: cada conexão usa um *Setup Token* do [SimpleFIN Bridge](https://bridge.simplefin.org/).

```
SIMPLEFIN_ENABLED=true
SIMPLEFIN_API_URL=https://beta-bridge.simplefin.org   # sandbox; bridge.simplefin.org para bancos reais
```

## Câmbio (opcional)

```
OPENEXCHANGERATES_APP_ID=...        # chave gratuita em openexchangerates.org
FX_SYNC_MODE=on_demand              # ou "scheduled"
```

Sem chave, valores entre moedas diferentes usam **câmbio 1:1** com aviso visual (e são corrigidos
depois pelas tarefas `restamp_*` quando houver taxas reais).

## Login OIDC (opcional)

Funciona com Authentik, Pocket ID e qualquer provedor OIDC padrão. Cadastre o redirect
`https://seu-host/api/auth/oidc/callback` (aplicação *confidential/web*).

```
OIDC_ENABLED=true
OIDC_PROVIDER_NAME=Pocket ID
OIDC_DISCOVERY_URL=https://id.exemplo.com/.well-known/openid-configuration
OIDC_CLIENT_ID=syncrofin
OIDC_CLIENT_SECRET=...
OIDC_SCOPES=openid email profile
OIDC_AUTO_REGISTER=true              # cria usuários no primeiro login
OIDC_REQUIRE_VERIFIED_EMAIL=true
OIDC_EXISTING_USER_LINK_MODE=disabled  # disabled | verified_email | email
```

| `OIDC_EXISTING_USER_LINK_MODE` | Comportamento |
|-------|---------------|
| `disabled` | Nunca vincula; usuários existentes continuam com senha. |
| `verified_email` | Vincula quando o provedor envia `email_verified=true` para o mesmo e-mail. |
| `email` | Vincula só pelo e-mail (use só se confiar totalmente no provedor). |

**Somente SSO:** `LOCAL_AUTH_ENABLED=false` (exige `OIDC_ENABLED`, `OIDC_CLIENT_ID` e
`OIDC_DISCOVERY_URL`, senão a aplicação recusa subir). Desativa senha, passkeys novas, registro,
recuperação de senha e novo TOTP; credenciais existentes não são apagadas. Na primeira subida
em modo SSO, o primeiro login precisa ser admin: mantenha `OIDC_AUTO_REGISTER=true`,
`OIDC_SYNC_ROLES=true` e um valor de `OIDC_ADMIN_ROLES` nos papéis da identidade.

**Sincronização de papéis:**

```
OIDC_SYNC_ROLES=true
OIDC_ROLES_CLAIM=groups
OIDC_ADMIN_ROLES=syncrofin-admins
OIDC_WORKSPACE_ROLE_MAP={"syncrofin-owners":"owner","syncrofin-editors":"editor","syncrofin-viewers":"viewer"}
```

`OIDC_ADMIN_ROLES` concede/revoga `is_superuser` a cada login; o mapa define o papel no workspace
pessoal (vale o maior quando há vários).

## Passkeys (WebAuthn)

Ligadas por padrão, sem configuração — seguem o endereço em que o app é aberto. Regras do padrão
WebAuthn (sem contorno): **IP nunca é válido** e **HTTP puro só em `localhost`**. Use
`http://localhost:3100` ou um domínio com HTTPS.

```
FRONTEND_URL=https://syncrofin.exemplo.com
# WEBAUTHN_RP_ID=syncrofin.exemplo.com   # fixa em um domínio (use o domínio-pai para subdomínios)
# WEBAUTHN_RP_NAME=SyncroFin             # nome exibido no prompt do navegador
# WEBAUTHN_ORIGIN=                       # fixa a origem esperada
```

## Armazenamento de anexos

Local por padrão (`STORAGE_LOCAL_PATH=/app/data/attachments`, volume `attachments`). Limites em
`config.py`: 10 MB por arquivo, 10 anexos por transação, 20 por fatura, extensões
`jpg,jpeg,png,webp,gif,heic,pdf`. Os campos de S3 existem no `config.py`, mas o provider S3 **não
está implementado** (só `local_storage.py`).

## Agentes de IA (opcional)

Desligado por padrão, custo zero quando desligado.

```
AGENTS_ENABLED=true
COMPOSE_PROFILES=agents                # sobe o container mcp-server (só Docker Compose)
AGENTS_MCP_JWT_SECRET=<segredo forte>  # assina tokens MCP (troque o padrão!)
```

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `AGENTS_DEFAULT_PROVIDER` | `ollama` | `ollama`, `openai`, `anthropic`, `openai_compatible` |
| `AGENTS_DEFAULT_MODEL` | — | Modelo padrão |
| `AGENTS_OLLAMA_BASE_URL` | `http://ollama:11434` | Use `http://host.docker.internal:11434` para Ollama no host |
| `AGENTS_OPENAI_API_KEY`, `AGENTS_ANTHROPIC_API_KEY` | — | Chaves globais (alternativa: conexões na UI) |
| `AGENTS_OPENAI_COMPAT_BASE_URL` / `_API_KEY` | — | LM Studio, llama.cpp, vLLM… |
| `AGENTS_EMBEDDING_PROVIDER` | `native` | `native` (fastembed local), `ollama`, `openai`, `openai_compatible` |
| `AGENTS_EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Modelo de embeddings |
| `AGENTS_BUILTIN_MCP_URL` | `http://mcp-server:8765/mcp` | Onde o backend encontra o MCP embutido |
| `AGENTS_EXTERNAL_MCP_URL` | — | URL pública do MCP para clientes externos (atrás de proxy) |
| `AGENTS_EXTRA_MCP_SERVERS` | — | Servidores MCP adicionais |
| `AGENTS_MCP_EXTERNAL_TTL_DAYS` | `90` | Validade dos tokens externos |
| `AGENTS_MCP_EXTERNAL_HOST_PORT` | `127.0.0.1:8765` | Publicação da porta MCP (`0.0.0.0:8765` expõe na LAN) |

**Sem Docker:** defina só `AGENTS_ENABLED=true`, rode
`uvicorn mcp_server.main:app --host 127.0.0.1 --port 8765` junto da API e aponte
`AGENTS_BUILTIN_MCP_URL=http://127.0.0.1:8765/mcp`. Sem esse servidor os agentes conversam, mas
sem acesso aos seus dados.

> Revogar tokens MCP externos = rotacionar `AGENTS_MCP_JWT_SECRET`.

## E-mail (SMTP) e webhook (opcional)

O **SMTP** serve a três coisas: **recuperação de senha**, **convites de workspace** (sem precisar inventar uma
senha para a pessoa) e os **alertas** (ver [FEATURES](FEATURES.md#3-notificações)). Sem SMTP o app funciona,
mas a tela "esqueci a senha" avisa que não há e-mail e convidar alguém novo exige definir a senha na hora. O
sino dentro do app funciona sempre. Configure um ou ambos os canais:

```
SMTP_HOST=smtp.exemplo.com
SMTP_PORT=587
SMTP_USER=alertas@exemplo.com
SMTP_PASSWORD=...
SMTP_FROM=SyncroFin <alertas@exemplo.com>   # obrigatório junto com SMTP_HOST
SMTP_STARTTLS=true

NOTIFICATIONS_WEBHOOK_URL=https://exemplo.com/hooks/syncrofin
NOTIFICATIONS_WEBHOOK_SECRET=...            # assina o corpo: X-SyncroFin-Signature: sha256=<hmac>
```

Sem `SMTP_HOST` + `SMTP_FROM` não há e-mail; sem `NOTIFICATIONS_WEBHOOK_URL` não há webhook. Os
destinatários são os membros `owner` e `editor` do workspace. As variáveis já são repassadas pelos dois
compose e pelo Helm chart (`config.smtp*`, `secret.smtpPassword`, `config.notificationsWebhookUrl`).

## Conciliação automática

Não é variável de ambiente: é uma configuração do workspace (Configurações do workspace → *Conciliação
automática*), disponível para *owners* de workspaces com o módulo de faturas.
