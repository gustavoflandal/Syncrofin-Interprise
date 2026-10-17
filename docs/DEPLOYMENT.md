# Deploy e operação

## Publicando uma versão

O pipeline (`.github/workflows/release.yml`) roda quando você envia uma tag de versão:

```bash
git tag vX.Y.Z && git push origin vX.Y.Z
```

Ele executa o mesmo CI de um pull request e, se passar, publica: as imagens
`ghcr.io/gustavoflandal/syncrofin-enterprise-backend` e `…/syncrofin-enterprise-frontend` (**linux/amd64 e linux/arm64**, com
as tags `X.Y.Z`, `X.Y` e `latest`; pré-releases como `vX.Y.Z-rc.1` não recebem `latest`), o chart Helm em
`oci://ghcr.io/gustavoflandal/charts-enterprise/syncrofin` e uma *release* no GitHub com notas geradas.

> **Os nomes são diferentes dos da Community de propósito** (`syncrofin-enterprise-*` e `charts-enterprise`): o mesmo dono publica
> as duas edições, e um nome igual faria uma sobrescrever a imagem da outra.

> **Os pacotes ficam privados, e devem ficar.** O repositório é privado e o GitHub cria cada pacote como privado; não os torne
> públicos. Para baixar as imagens é preciso estar autenticado:
>
> - **Docker Compose / `install.sh`:** `docker login ghcr.io` com o seu usuário do GitHub e um *personal access token* com o
>   escopo `read:packages`. Quem só vai *usar* o sistema pode receber um token só de leitura.
> - **Kubernetes (Helm):** crie um segredo de registro e aponte para ele em `imagePullSecrets`:
>
>   ```bash
>   kubectl create secret docker-registry ghcr --docker-server=ghcr.io \
>     --docker-username=<usuário> --docker-password=<token com read:packages>
>   helm install syncrofin ./charts/syncrofin --set 'imagePullSecrets[0].name=ghcr' ...
>   ```

Construir manualmente (sem o pipeline):

```bash
docker build -t ghcr.io/gustavoflandal/syncrofin-enterprise-backend:latest  ./backend
docker build -t ghcr.io/gustavoflandal/syncrofin-enterprise-frontend:latest ./frontend \
  --build-arg VITE_APP_VERSION=vX.Y.Z
```

- Backend: `python:3.14-slim`, dependências instaladas a partir do `uv.lock` com hashes.
- Frontend: build Vite + `nginx-unprivileged` (porta 8080), proxy `/api/` → `BACKEND_URL`.

## Docker Compose de produção

```bash
cp .env.example .env
# preencha: SECRET_KEY, POSTGRES_PASSWORD e (se usar agentes) AGENTS_MCP_JWT_SECRET, além de FRONTEND_URL e credenciais de bancos
docker compose -f docker-compose.prod.yml up -d
```

Ou use o `install.sh`, que gera `SECRET_KEY`, `POSTGRES_PASSWORD` e `AGENTS_MCP_JWT_SECRET` aleatórios.

### Segredos obrigatórios (sem valores padrão)

Os valores de exemplo do repositório são **públicos**; quem os mantém assina os tokens de login e abre o banco com uma
senha que qualquer pessoa pode ler. Por isso não há mais padrão para eles:

| O que | Onde falta → o que acontece |
|-------|-----------------------------|
| `SECRET_KEY` e `POSTGRES_PASSWORD` | **Compose de produção:** `docker compose` recusa subir e diz qual variável falta. |
| `SECRET_KEY` (32+ caracteres), senha do Postgres ≠ `postgres` em host de rede, `AGENTS_MCP_JWT_SECRET` (com agentes ligados) | **Backend:** recusa iniciar se receber o valor de exemplo (ou vazio), listando o que corrigir (`app/core/secrets_guard.py`). |
| `secret.secretKey`, `postgresql.password`, `secret.agentsMcpJwtSecret` (agentes ligados) | **Helm:** `helm template/install` falha com a mensagem do comando para gerar o valor. |

Gerar: `openssl rand -hex 32` (chaves) e `openssl rand -hex 24` (senha do Postgres; só letras e números, porque vai dentro da
`DATABASE_URL`). `DEBUG=true` desliga essa verificação e é o que o compose de **desenvolvimento** usa; o de produção e o
chart nunca o ligam.

> **Já tem uma instalação rodando com a senha `postgres`?** Trocar `POSTGRES_PASSWORD` no `.env` **não** muda a senha do
> usuário no banco existente (o Postgres só lê essa variável ao criar o volume). **Antes de atualizar**, altere a senha
> dentro do banco:
>
> ```bash
> docker compose -f docker-compose.prod.yml exec db psql -U postgres -c "ALTER USER postgres PASSWORD '<a nova senha>'"
> ```
>
> Depois ponha a mesma senha no `.env` (`POSTGRES_PASSWORD`) e suba a versão nova. Sem esse passo o backend não conecta.

Antes de expor na internet, confira também:

- `FRONTEND_URL` do serviço `frontend` segue `FRONTEND_URL` (padrão `http://localhost:3100`) (só afeta o que o nginx expõe; a URL pública do sistema é a do backend).
- Coloque **HTTPS** na frente (necessário para passkeys, OAuth de bancos e para instalar o app no celular):
  use o `docker-compose.https.yml` da seção abaixo e mantenha `TRUSTED_PROXY_HOPS` coerente com a quantidade
  de proxies.

`install.sh` automatiza o fluxo em Linux/macOS (gera `.env` com `SECRET_KEY` aleatória, faz pull
e sobe o compose de produção), mas depende das imagens publicadas.

## Cabeçalhos de segurança HTTP

O nginx do frontend envia, em **todas** as respostas (app, `sw.js`, manifesto, `index.html` e `/api/`, inclusive erros):

| Cabeçalho | Valor | Por quê |
|-----------|-------|---------|
| `Content-Security-Policy` | `default-src 'self'`; scripts só do próprio app; `frame-ancestors 'none'`; ver abaixo | Bloqueia script injetado (XSS) e uso do sistema dentro de outro site. |
| `X-Content-Type-Options` | `nosniff` | O navegador não "adivinha" tipos de arquivo. |
| `X-Frame-Options` | `DENY` | Não deixa embutir o sistema em `<iframe>` (clickjacking). |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Não vaza caminhos internos para outros sites. |
| `Permissions-Policy` | câmera, microfone, localização, pagamento, USB, Bluetooth desligados | O sistema não usa. |
| `Cross-Origin-Opener-Policy` | `same-origin` | Isola a janela do sistema. |
| `Strict-Transport-Security` | `max-age=31536000` **só** quando a requisição chegou por HTTPS (`X-Forwarded-Proto: https`) | HSTS por HTTP puro seria ignorado; o Caddy do `docker-compose.https.yml` também o envia. |

Também: `server_tokens off` (a versão do nginx não aparece).

**A política de conteúdo** (`frontend/security-headers.inc.template`) só libera o que o app usa: estilos inline (React e a biblioteca
de componentes usam `style=""`), imagens `https:` (logos de bancos e de ativos vêm de outros hosts), `blob:` para a prévia de PDF e
imagens de anexos. **Nada é buscado de outro site**: a fonte (Geist) agora vai junto com o app, em vez de vir do Google Fonts. Isso
também tira do navegador do usuário uma requisição a um terceiro a cada acesso.

- **Acrescentar uma origem** (por exemplo, uma API que você integrou): variável `CSP_CONNECT_EXTRA` do container do frontend
  (separada por espaços). Padrão: vazia.
- **Aviso de nova versão:** o navegador **não consulta** o GitHub por padrão (isso avisaria a um terceiro que sua instância existe, e um
  repositório privado não tem o que responder). Para ligar, compile o frontend com `VITE_RELEASES_API_URL`
  (`https://api.github.com/repos/<dono>/<repo>/releases/latest`) e ponha `https://api.github.com` em `CSP_CONNECT_EXTRA`.

Um teste (`frontend/src/security-config.test.ts`) falha se uma `location` nova do nginx esquecer de incluir os cabeçalhos (o nginx
descarta o `add_header` do servidor em qualquer `location` que tenha o seu), se a política liberar script inline ou outra origem, ou
se o `index.html` voltar a carregar algo de fora.

## HTTPS (Caddy) e app no celular

`docker-compose.https.yml` + `deploy/caddy/Caddyfile` acrescentam um **Caddy** com certificado Let's Encrypt
emitido e renovado sozinho. O manual do sistema traz o passo a passo para o administrador (tópico *Publicar com
HTTPS*, também em [MANUAL.md](MANUAL.md)); em resumo:

1. Registro DNS **A/AAAA** do domínio → IP público do servidor; portas **80 e 443** liberadas.
2. No `.env`: `DOMAIN=syncrofin.exemplo.com` e uma `SECRET_KEY` forte.
3. `docker compose -f docker-compose.prod.yml -f docker-compose.https.yml up -d`
   (ou `COMPOSE_FILE=docker-compose.prod.yml:docker-compose.https.yml` no `.env`).
4. `docker compose ... logs -f caddy` até aparecer `certificate obtained successfully`.
5. Abrir `https://<domínio>`, criar o administrador e desativar o registro público.

O que o overlay faz: publica só o Caddy (80/443); tira as portas do frontend e do backend do host; define
`FRONTEND_URL=https://$DOMAIN` (CORS, links de e-mail, passkeys) e **`TRUSTED_PROXY_HOPS=2`** no backend e nos
workers. O `2` é a cadeia navegador → Caddy → nginx do frontend → backend: com `1` todos os usuários cairiam no
mesmo balde do limitador de tentativas (o IP do Caddy). Requer Docker Compose ≥ 2.24 (`!reset`).

**Verificado** com Caddy 2 e o nginx do frontend, em containers: o proxy repassa `/api` e o manifesto, envia
`Strict-Transport-Security`, **descarta um `X-Forwarded-For` forjado pelo cliente** e o backend recebe
`X-Forwarded-For: <cliente>, <caddy>` (por isso `2`). **Não verificado:** emissão real do certificado (exige domínio
e portas públicas) e a instalação em um celular físico.

Sem IP público (CGNAT) ou só uso privado: um túnel (Tailscale, Cloudflare Tunnel) entrega o HTTPS; nesse caso use só o
`docker-compose.prod.yml`, aponte o túnel para a porta do frontend e ajuste `FRONTEND_URL` e `TRUSTED_PROXY_HOPS`.
Esse caminho **não foi testado**.

## Kubernetes (Helm)

```bash
helm install syncrofin ./charts/syncrofin \
  --set global.domain=syncrofin.exemplo.com
```

- Pré-requisitos: Kubernetes 1.25+, Helm 3.2+, PostgreSQL 15+ **com `pgvector`**, Redis 7+
  (o chart inclui StatefulSets opcionais de Postgres e Redis).
- Ingress clássico ou **Gateway API** (`HTTPRoute`).
- Backend, worker e MCP server compartilham PVCs (anexos e conhecimento): em cluster
  multi-nó, use StorageClass **RWX** ou restrinja tudo a um único nó.
- Segredos: prefira `global.existingSecret` a colocar chaves no `values.yaml`.
- Migrações rodam num `Job` (`templates/backend/job-migration.yaml`).
- Detalhes em `charts/syncrofin/README.md`. `helm install syncrofin oci://ghcr.io/gustavoflandal/charts-enterprise/syncrofin --version <X.Y.Z>`
  vale depois da primeira publicação (com `helm registry login ghcr.io`, porque o pacote é privado).

## Backups

- **Aplicação:** a UI oferece backup ZIP criptografado com senha (AES-256) —
  `/api/export/backup` (`services/backup_service.py`). A senha não é guardada; sem ela o arquivo
  não é recuperável.
- **Banco:** ative o perfil `backup` (`COMPOSE_PROFILES=backup` no `.env`, ou `--profile backup`): dump diário
  (`db-backup`), base backup semanal (`db-basebackup`) e WAL contínuo para PITR (RPO <= 15 min, RTO <= 2 h). No Helm:
  `--set backup.enabled=true`. Teste com `backend/scripts/restore_drill.sh`. Detalhes em [ADMIN §6](ADMIN.md#6-backups-e-recuperação).
  Manual: `docker compose exec db pg_dump -U postgres syncrofin_enterprise > syncrofin.sql`
- **Arquivos:** volumes `attachments` e `agent_knowledge`.
- **Segredos a guardar fora do repositório:** `.env`, `secrets/*.pem`. Perder `SECRET_KEY`
  invalida sessões; as chaves de LLM salvas no banco são cifradas com chave derivada da
  `SECRET_KEY`, então **trocá-la torna essas conexões ilegíveis** (recadastre-as).

## Atualização

```bash
git pull
docker compose up -d --build     # o backend roda `alembic upgrade head` ao iniciar
```

Migrações são só "para frente" na prática — faça backup do banco antes de atualizar.

### Infraestrutura Docker própria (e como mudar de uma instalação antiga)

A edição Enterprise tem a **sua própria infraestrutura Docker**, para poder rodar na mesma máquina que a Community
sem misturar nada:

| | Enterprise | Community |
|---|---|---|
| Projeto do Compose (prefixo dos contêineres, volumes e rede) | `syncrofin-enterprise` | `syncrofin` |
| Banco de dados | `syncrofin_enterprise` | `syncrofin` |
| Portas no host (frontend / API) | `3100` / `8100` | `3000` / `8000` |
| Banco dos testes | projeto `syncrofin-enterprise-test`, porta `55433` | `syncrofin-test`, porta `55432` |
| Imagens | `syncrofin-enterprise-backend` / `-frontend` | `syncrofin-backend` / `-frontend` |
| Chart Helm publicado em | `oci://ghcr.io/<dono>/charts-enterprise` | `oci://ghcr.io/<dono>/charts` |

As portas se mudam com `FRONTEND_PORT` e `BACKEND_PORT` no `.env`.

Quem já tinha uma instalação com um nome anterior (projeto `financebr` ou `syncrofin`) tem os dados em volumes com o
prefixo antigo. **`scripts/migrate-docker-project.sh`** move tudo para o projeto novo sem apagar nada: para o
projeto antigo, copia os volumes, renomeia o banco e sobe a pilha nova.

```bash
git pull
scripts/migrate-docker-project.sh financebr        # ou: syncrofin
# em produção: scripts/migrate-docker-project.sh financebr financebr docker-compose.prod.yml
```

O script termina dizendo como remover os volumes antigos, o que só vale a pena depois de conferir a instalação nova.
Instalações novas não precisam disto.

### Segundo fator obrigatório e trancamento

`REQUIRE_MFA=true` no `.env` exige o segundo fator de todos, **imediatamente**, e o painel não desfaz. Antes de ligar, o
administrador precisa ter o próprio 2FA configurado. Se ninguém conseguir entrar: reinicie sem `REQUIRE_MFA` (ou com
`false`) e, se a regra foi ligada pelo painel, desligue-a no banco
(`UPDATE app_settings SET value='false' WHERE key='mfa_required';`). Para um usuário que perdeu o celular, use
**Administração → Editar usuário → Redefinir 2FA**. Detalhes em [FEATURES §11](FEATURES.md#11-verificação-em-duas-etapas-obrigatória).

## Segurança — checklist

- [ ] `SECRET_KEY` e `AGENTS_MCP_JWT_SECRET` fortes e únicos
- [ ] Senha do Postgres alterada; banco sem porta publicada no host
- [ ] HTTPS na frente do frontend (`docker-compose.https.yml`); `FRONTEND_URL` correto e `TRUSTED_PROXY_HOPS` = nº de proxies
- [ ] Registro público desativado no painel admin se for uso pessoal
- [ ] 2FA/passkey ligados para o admin
- [ ] Porta MCP (8765) não exposta à internet (padrão: `127.0.0.1`)
- [ ] `.env` e `secrets/` fora do git
