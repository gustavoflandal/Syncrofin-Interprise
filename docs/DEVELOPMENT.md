# Guia de desenvolvimento

## Pré-requisitos

| Ferramenta | Versão | Para quê |
|-----------|--------|----------|
| Docker + Compose | recente | Stack completa (recomendado) e **banco dos testes** |
| Python | 3.11+ (a imagem usa 3.14) | Backend/testes fora do Docker |
| [uv](https://docs.astral.sh/uv/) | 0.12.x | Lockfile do backend (`uv.lock`) |
| Node.js | 22+ | Frontend |

## Subindo o ambiente

```bash
cp .env.example .env            # opcional
docker compose up --build       # db, redis, backend, frontend, celery-worker, celery-beat
docker compose --profile agents up   # + servidor MCP (com AGENTS_ENABLED=true)
```

- Frontend <http://localhost:3100> · API <http://localhost:8100/api/docs>
- Backend e frontend rodam com **hot reload** (código montado como volume).
- Portas: `FRONTEND_PORT` / `BACKEND_PORT` no `.env` se houver conflito.
- Reset total do ambiente local: `docker compose down -v` (apaga os volumes — inclusive o banco).

### Sem Docker (backend)

Precisa de PostgreSQL 16 (com `pgvector`) e Redis locais e das variáveis `DATABASE_URL`,
`REDIS_URL`, `SECRET_KEY`.

```bash
cd backend
uv sync --all-extras            # ou: python -m venv .venv && pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
celery -A app.worker worker --loglevel=info      # processo separado
celery -A app.worker beat --loglevel=info        # processo separado
```

### mise (opcional)

`mise //...:install`, `mise backend:test`, `mise frontend:lint`, `mise frontend:build`.

## Testes e qualidade

### Backend

Os testes rodam **somente em PostgreSQL real** (com a extensão `pgvector`), o mesmo motor da produção. Não há
fallback para SQLite: ele escondia comportamento específico do Postgres (`to_char`, collation, chaves
estrangeiras, `pgvector`) atrás de *shims* e de testes pulados.

```bash
docker compose -f docker-compose.test.yml up -d      # Postgres descartável em localhost:55433 (tmpfs)
cd backend
pytest -n 4                     # ~3.960 testes, ~12 min com 4 workers (não use -n auto em máquina com muitos núcleos:
                                # dezenas de workers esgotam os locks do Postgres de teste)
pytest tests/test_transactions_api.py -k transfer
ruff check .                    # regras E4, E7, E9, F; linha de 100 colunas
ty check .                      # type checker (ty 0.0.81, versão fixada)
python scripts/check_migration_chain.py    # uma única cabeça de migração
```

- **Banco:** `TEST_DATABASE_URL` (padrão `postgresql+asyncpg://postgres:postgres@localhost:55433/postgres`)
  aponta para qualquer servidor onde o usuário possa `CREATE DATABASE` e `CREATE EXTENSION`. **Cada worker do
  xdist recebe o próprio banco** (`syncrofin_test_gw0`…), então `-n 4` não mistura linhas. O esquema é
  criado dos modelos a cada sessão; entre testes as tabelas são esvaziadas com `TRUNCATE … CASCADE`.
- **Migrações são testadas de verdade** (`tests/test_migrations_postgres.py`): num banco novo, `alembic
  upgrade head` deve produzir exatamente as tabelas e colunas dos modelos, e as duas últimas migrações
  devem ser reversíveis. É o que pega um campo de modelo sem migração.
- Como o Postgres impõe chaves estrangeiras, um teste que insere `workspace_id`/`connection_id` inventado
  falha: crie a linha-pai de verdade. Quando o SQLAlchemy não conhece o relacionamento, dê `flush()` na linha-pai
  antes de adicionar a filha.
- `conftest.py` liga `AGENTS_ENABLED=true` e usa segredos sintéticos.
- Padrões de teste: um `test_<recurso>_api.py` (HTTP) e um `test_<recurso>_service.py` (regra),
  além de `*_coverage.py` que fecham lacunas de cobertura.
- Hooks de pré-commit (opcionais): `.pre-commit-config.yaml` (ruff, cadeia de migrações, ty).

### CI

`.github/workflows/ci.yml` roda em PR e push na `main`: backend (uv lock, cadeia de migrações, ruff, ty, pytest com
serviço `pgvector/pgvector:pg16`), frontend (lint, typecheck, `i18n:check --strict`, vitest, build),
artefatos de deploy (compose, `helm lint`/`template`, build das duas imagens) e uma auditoria de
dependências informativa. Publicação: veja [DEPLOYMENT](DEPLOYMENT.md).

### Frontend

```bash
cd frontend
npm ci
npm run typecheck               # tsc nativo (TypeScript 7)
npm run lint                    # eslint (inclui jsx-a11y)
npm test                        # vitest (~780 testes)
npm run i18n:check              # cobertura de traduções (--strict falha se en/pt-BR divergirem)
npm run build
```

Não há falhas conhecidas: backend e frontend passam por inteiro. Se um teste falhar, é uma regressão (ou um
teste novo instável: corrija-o em vez de reexecutar).

## Ambiente de avaliação local (com e-mail de teste)

Para experimentar o produto inteiro, inclusive recuperação de senha e convites, sem enviar e-mail de verdade:

```bash
# .env (ignorado pelo git)
SECRET_KEY=<openssl rand -hex 32>
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_STARTTLS=false
SMTP_FROM=SyncroFin <no-reply@syncrofin.local>

# docker-compose.override.yml (ignorado pelo git)
services:
  mailpit:
    image: docker.io/axllent/mailpit:latest
    ports: ["8025:8025"]

docker compose up -d --build
```

Abra <http://localhost:3100> (o primeiro acesso cria o administrador) e a caixa de e-mail de teste em
<http://localhost:8025>. Para recomeçar do zero: `docker compose down -v`. Use um domínio real de e-mail nos
cadastros (`example.com` serve); domínios reservados como `.local` são recusados pela validação.

> Se o build de uma imagem falhar por um binário opcional ausente (`@rolldown/binding-linux-x64-gnu`, por
> exemplo), foi um download interrompido: reconstrua com `docker compose build --no-cache frontend` e
> recrie o volume com `docker compose up -d --force-recreate -V frontend`.

## Migrações de banco (Alembic)

```bash
cd backend
alembic revision -m "descricao_curta"     # crie manualmente: NNN_descricao.py
alembic upgrade head
alembic downgrade -1
```

- Numeração **sequencial de 3 dígitos** (`091_...`), `down_revision` apontando para a anterior.
  O script `check_migration_chain.py` falha se houver duas cabeças (colisão de números entre
  branches).
- Migrações rodam automaticamente ao subir o `backend` no Compose.
- Ao adicionar coluna a modelo existente, dê `server_default` para não quebrar linhas antigas.

## Dependências

- **Backend:** edite `pyproject.toml` e rode `backend/scripts/lock.sh` (gera `uv.lock`). A imagem
  Docker instala a partir do lock com verificação de hash (`--require-hashes`). Não commite
  mudanças em `pyproject.toml` sem o `uv.lock` correspondente.
- **Frontend:** `npm install <pkg>` atualiza `package-lock.json` (commite). O `.npmrc` tem
  regras de segurança para pacotes recém-publicados.
- `renovate.json` está configurado para abrir PRs de atualização (requer o app Renovate no repo).

## Internacionalização (i18n)

O produto fala **três idiomas**: `en`, `pt-BR` e `es` (`frontend/src/locales/`). Os demais idiomas do projeto
original foram removidos (continuam no histórico do git).

- Textos ficam em `frontend/src/locales/<idioma>.json`; use `t('chave')` (react-i18next).
- `en` é a fonte de verdade e o fallback; `pt-BR` também é empacotado no bundle principal e `es` carrega sob demanda.
- Ao criar uma chave nova, adicione **aos três** (a suíte, `i18n.test.ts`, exige paridade) e rode
  `npm run i18n:check -- --strict`.
- A lista de idiomas vive em **um lugar**: `SUPPORTED_LANGS` em `src/lib/i18n.ts` (os dois menus de idioma
  são gerados dela). Quem tinha escolhido um idioma removido cai em inglês.
- Para **adicionar um idioma**: crie o JSON com todas as chaves, inclua a entrada em `SUPPORTED_LANGS`, em
  `resolveSupportedLang`, em `supportedLngs` (mesmo arquivo), em `date-fns-locale.ts` e em `MAINTAINED`
  (`scripts/check-locales.mjs`); e o idioma dos e-mails em `backend/app/services/email_templates.py`.
- O idioma padrão é **português (pt-BR)** para quem ainda não escolheu: `DEFAULT_LANGUAGE` em `lib/i18n.ts`. Uma escolha guardada vale
  mais, e o idioma do navegador **não** é seguido de propósito. `fallbackLng` continua **inglês**: é para tradução que falta, outra
  pergunta. No backend, os padrões de uma conta nova (idioma, moeda, formato de data, fuso) vêm de `app/core/defaults.py` e das
  variáveis `DEFAULT_LANGUAGE`, `DEFAULT_CURRENCY`, `DEFAULT_DATE_FORMAT`, `DEFAULT_TIMEZONE` (padrão: pt-BR, BRL, DD/MM/YYYY,
  America/Sao_Paulo). Categorias e carteira iniciais seguem o idioma da conta. Os testes do frontend fixam o inglês em `test/setup.ts`.

## Manual e ajuda em cada tela

O manual do usuário vive em `frontend/src/help/content/pt-BR/*.md` e alimenta duas coisas: o botão **?** de cada
tela (painel lateral) e a página `/help`. Detalhes em [FEATURES §8](FEATURES.md#8-manual-e-ajuda-em-cada-tela).

- **Editar uma página:** altere o `.md`, depois `npm run manual:build` (em `frontend/`) para atualizar
  `docs/MANUAL.md` (o CI confere com `npm run manual:check`). Comece com um `# Título`; ligue a outras páginas
  com `[texto](help:<tópico>)`.
- **Tela nova:** adicione a rota em `App.tsx` **e** o caminho ao tópico certo em `src/help/topics.ts` (ou crie um
  tópico novo, com o `.md`). `topics.test.ts` falha se esquecer.
- **Tópico novo:** entrada em `TOPICS` (id, seção, caminhos) + `content/pt-BR/<id>.md`; algum outro tópico deve
  apontar para ele.
- **Novo idioma do manual:** crie `content/<idioma>/` com as páginas que já tiver traduzido; as demais caem em
  português com aviso. (O idioma também precisa existir na interface — ver i18n acima.)
- **Imagens:** uma página pode mostrar telas com `![descrição](/manual-img/<tópico>/<arquivo>.png)`. Os arquivos ficam em
  `frontend/public/manual-img/` (não em `/help/`, que é rota do manual). Só esse prefixo é aceito (nada de outro site, `data:` ou
  `..`); a descrição é obrigatória e vira a legenda. `topics.test.ts` falha se a imagem não existir, se não tiver descrição ou se
  sobrar arquivo que nenhuma página usa. `manual:build` reescreve o caminho para `docs/MANUAL.md`. Para as telas do app Android: use
  dados **inventados** (usuário de demonstração), capture com `adb exec-out screencap -p` num build de **debug** (o release bloqueia
  capturas), corte a barra de status (tem ícones de notificação pessoais) e reduza para ~540 px de largura (20 a 50 KB cada).
- Escreva só o que o sistema faz **de fato**; confira nome de botão e regra no código ou nos textos de
  `locales/pt-BR.json` antes de documentar.

## Dependências e vulnerabilidades

O job *Dependency audit* do CI (`pip-audit` no backend, `npm audit --omit=dev` no frontend) é **informativo**:
não bloqueia PR, mas deve ficar verde. Ao aparecer um achado:

- **Corrija subindo a versão** quando existe correção (`uv lock --upgrade-package <pacote>`, `npm install <pacote>@^X`),
  rode a suíte inteira e só então faça o PR. Pacotes de criptografia (`cryptography`) merecem atenção: mexem
  nos backups e nas chaves de LLM salvas (`agents/services/crypto.py`).
- **Ignore só com justificativa escrita**, no workflow, quando o achado não se aplica. Único caso hoje:
  `PYSEC-2026-1325` (`ecdsa`, ataque de temporização ao *assinar* com ECDSA, sem correção publicada). Não se aplica:
  o `python-jose` só usa o `ecdsa` se o `cryptography` estiver ausente (`jose.backends.ECKey` resolve para
  `cryptography_backend`, conferido), e o sistema assina apenas com HS256 (tokens MCP) e RS256 (Enable Banking); ES256 só é
  *verificado* (OIDC), e a verificação não é afetada. Se o `python-jose` for trocado por PyJWT algum dia, cuidado:
  o PyJWT **não valida `at_hash`** do id_token OIDC, e hoje o `python-jose` valida (`access_token=` em `oidc_auth.py`).
- O `.npmrc` tem `min-release-age=7`: o npm ignora versões com menos de 7 dias como proteção contra pacote
  malicioso recém-publicado.

## Como adicionar uma funcionalidade (roteiro)

1. **Modelo** em `backend/app/models/` (com `workspace_id`) + registre em `models/__init__.py`.
2. **Migração** `NNN_*.py`.
3. **Schema** Pydantic em `schemas/`.
4. **Serviço** em `services/` (regra de negócio; sem lógica na rota).
5. **Rota** em `api/` usando a dependência de contexto de workspace; chame `require_write()` em
   escritas; registre o router em `app/main.py`.
6. **Testes** de API e de serviço.
7. **Frontend:** tipo em `src/types/index.ts`, chamada em `src/lib/api.ts`, página/componente,
   rota em `App.tsx`, item em `lib/nav-items.ts` e (se for módulo) em `lib/modules.ts` +
   `services/module_service.py`.
8. **Traduções** (`en`, `pt-BR`).
9. Se for opcional/pesado, proteja com feature flag (`core/feature_flags.py`, `/api/info`).

## Adicionando um provider bancário

Implemente `BankProvider` (`providers/base.py`), registre com `register_provider` e adicione a
entrada em `KNOWN_PROVIDERS` (`providers/__init__.py`). Escolha o `flow_type`
(`widget`/`oauth`/`token`). Cubra com testes em `tests/test_providers_<nome>.py` (os providers
reais ficam fora da cobertura — ver `[tool.coverage.run]` no `pyproject.toml`).

## Dados de teste e performance

`backend/scripts/seed_perf.py` popula ~100 mil transações para testes de carga
(`docker compose exec backend python scripts/seed_perf.py --scale 0.1`). Detalhes em
`backend/scripts/README.md`.

## Depuração

| Sintoma | Onde olhar |
|---------|-----------|
| API 500 | `docker compose logs -f backend`; `DEBUG=true` (padrão no dev) liga o log de SQL |
| Sync bancário não roda | `docker compose logs -f celery-worker celery-beat`; Redis saudável? |
| "Migration has multiple heads" | `python backend/scripts/check_migration_chain.py` |
| Frontend não alcança a API | `BACKEND_URL` do serviço `frontend`; proxy `/api` no `vite.config.ts` |
| Passkey não registra | Só funciona em `localhost` ou HTTPS com domínio (nunca IP) — ver CONFIGURATION |
| Agentes sem ferramentas | Servidor MCP não está de pé / `AGENTS_BUILTIN_MCP_URL` incorreta |

## Convenções de código

- Backend: async em tudo que toca o banco; `Decimal` para dinheiro; datas como `date`; comentários
  explicam o **porquê** (o código herdado é bem documentado — mantenha o padrão).
- Frontend: componentes funcionais, hooks, `@/` para imports, testes ao lado do arquivo.
- Commits: Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`…), o que também permite
  gerar changelog automaticamente depois.
- Nunca commite `.env`, `secrets/`, dados de `backend/data/` ou arquivos `celerybeat-schedule*`
  (já estão no `.gitignore`).
