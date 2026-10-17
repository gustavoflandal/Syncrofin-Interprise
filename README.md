<p align="center">
  <img src="docs/logo.svg" width="160" alt="Logo do SyncroFin" />
</p>

<h1 align="center">SyncroFin</h1>

**Gestor de finanças pessoais e de pequenos negócios, open source e self-hosted.**
Seus dados ficam na sua infraestrutura — nenhuma empresa fica entre você e o seu dinheiro.

> **Edição Enterprise.** Este repositório é a edição **Enterprise** do SyncroFin: parte da versão Community
> [v0.17.0](https://github.com/gustavoflandal/SyncroFin/releases/tag/v0.17.0) e recebe o que o
> [plano empresarial](docs/ENTERPRISE.md) pede (auditoria, permissões granulares, sessões seguras, LGPD, fiscal,
> integrações). A Community fica só com correções, que chegam aqui por `git merge`. Regras em
> [docs/EDITIONS.md](docs/EDITIONS.md). **Ainda não há versão publicada desta edição.**

> **Origem:** o SyncroFin nasceu de um *fork* do [Securo](https://github.com/securo-finance/securo)
> (v0.16.0, AGPL-3.0) e **segue como projeto independente**: não acompanha o upstream. O código
> herdado mantém seus créditos e a licença AGPL-3.0 (arquivo `LICENSE`).

---

## Recursos

- **Contas e transações** — várias contas com saldo corrente, busca, filtros e exportação CSV
- **Importação de arquivos** — OFX, QIF, CAMT e CSV (com mapeamento de colunas)
- **Regras de categorização** automáticas e **conciliação** (sugestões, histórico, regras portáveis)
- **Recorrências, orçamentos e metas** com acompanhamento de progresso
- **Cartões de crédito** com faturas (convenção brasileira de fechamento/vencimento)
- **Patrimônio** — ativos com histórico de valor, regras de crescimento, cotações de mercado e
  **Tesouro Direto**; livro de operações com **preço médio** por ticker
- **Relatórios** — patrimônio líquido e receitas × despesas, com sparklines por categoria
- **Sincronização bancária** — Pluggy (bancos brasileiros / Open Finance), Enable Banking
  (PSD2, Europa) e SimpleFIN (EUA/internacional)
- **Multimoeda** com conversão automática de câmbio
- **Workspaces** (pessoal ou negócio) com papéis `owner` / `editor` / `viewer`
- **Faturas (invoices)** para workspaces de negócio, com PDF e link público compartilhável
- **Divisão de despesas** em grupos, com liquidação entre membros
- **Segurança** — 2FA (TOTP), passkeys (WebAuthn), login OIDC, limite de tentativas
- **Agentes de IA** *(opcional)* — chat com LLM (Ollama, OpenAI, Anthropic ou compatível) com
  acesso aos seus dados via MCP e base de conhecimento (RAG) por agente
- **App no celular** — PWA instalável (Android, iPhone e computador) com HTTPS automático via Caddy (`docker-compose.https.yml`); passo a passo no manual
- **App Android** (`mobile/`): login, lançar movimento, listar lançamentos e fotografar o comprovante; usa a API existente. Veja [mobile/README.md](mobile/README.md)
- **3 idiomas** na interface: português (BR), inglês e espanhol
- **Manual e ajuda em cada tela** — botão **?** (ou tecla `?`/`F1`) abre a página da tela atual; o manual completo, com busca, fica em `/help`
- Backup criptografado (ZIP AES-256) e exportação dos dados

## Stack

| Camada | Tecnologias |
|--------|-------------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy 2 (async), Alembic, fastapi-users |
| Tarefas | Celery (worker + beat) sobre Redis |
| Banco | PostgreSQL 16 (imagem `pgvector`, usada pelos agentes) |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, shadcn/ui (Radix) |
| Infra | Docker Compose, Helm chart (Kubernetes), nginx |

## Início rápido (desenvolvimento)

Pré-requisito: [Docker](https://www.docker.com/products/docker-desktop/) com Compose.

```bash
git clone https://github.com/gustavoflandal/SyncroFin.git
cd SyncroFin
cp .env.example .env        # opcional: defina SECRET_KEY e credenciais de integrações
docker compose up --build
```

Abra <http://localhost:3100>. No primeiro acesso a tela `/setup` cria o usuário administrador.

| Serviço | Endereço |
|---------|----------|
| Frontend (Vite) | <http://localhost:3100> |
| API + Swagger | <http://localhost:8100/api/docs> |
| Servidor MCP *(perfil `agents`)* | `127.0.0.1:8765` |

> O `docker-compose.prod.yml` e o `install.sh` dependem de imagens publicadas em
> `ghcr.io/gustavoflandal/syncrofin-enterprise-*`, **privadas** (exigem `docker login ghcr.io`) e **ainda não publicadas**: elas
> saem quando uma tag `vX.Y.Z` for enviada.
> Até lá, use o `docker-compose.yml`, que constrói a partir do código-fonte.

## Desenvolvimento

```bash
# Backend (Python 3.11+)
cd backend
pip install -e ".[dev]"
pytest                      # usa SQLite em memória, não precisa de Postgres
ruff check .

# Frontend (Node 22+)
cd frontend
npm ci
npm run dev                 # typecheck: npm run typecheck · testes: npm test · lint: npm run lint
```

O guia completo (migrações, i18n, convenções, depuração) está em
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Documentação

| Documento | Conteúdo |
|-----------|----------|
| [docs/MANUAL.md](docs/MANUAL.md) | Manual do usuário completo (o mesmo da ajuda dentro do sistema) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Arquitetura, módulos do backend e frontend, modelo de dados, fluxos principais |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Ambiente local, testes, migrações, convenções, como adicionar funcionalidades |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Variáveis de ambiente: bancos, OIDC, passkeys, câmbio, agentes de IA |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker Compose de produção, HTTPS (Caddy), Helm chart, backups e segurança |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Diagnóstico do projeto e backlog priorizado de melhorias |
| [docs/EDITIONS.md](docs/EDITIONS.md) | Community × Enterprise: como as duas se relacionam, migrações, publicação e licença |
| [docs/ENTERPRISE.md](docs/ENTERPRISE.md) | Requisitos e plano de implementação para uso empresarial |
| [CLAUDE.md](CLAUDE.md) | Contexto resumido para continuar o trabalho com o Claude Code |

## Segurança

Veja [SECURITY.md](SECURITY.md). Nunca versione `.env` nem arquivos em `secrets/`
(ambos estão no `.gitignore`).

