# SyncroFin — contexto para o Claude Code

Gestor de finanças self-hosted, nascido de um fork do Securo v0.16.0 (AGPL-3.0) e **desenvolvido de forma
independente** (sem acompanhar o upstream). Responda em **português do Brasil**.
Documentação completa em `docs/` — leia `docs/ARCHITECTURE.md` antes de mexer no núcleo e
`docs/ROADMAP.md` para o backlog priorizado, `docs/ENTERPRISE.md` para o plano de uso empresarial e
`docs/FEATURES.md` para os recursos próprios (contador, saúde/previsão, notificações, conciliação automática, PWA).

## Edição Enterprise (este repositório)

Este é o **SyncroFin Enterprise**, derivado da Community v0.17.0. Leia `docs/EDITIONS.md` antes de mexer.
- Correções de bug/segurança são feitas **primeiro na Community** e trazidas com `git merge community/main`
  (nunca o contrário). Funcionalidade nova fica **só aqui**, de preferência em módulos novos.
- Migrações continuam a numeração da Community (`092` → `093`…); o caminho de volta não existe.
- Imagens e chart **já** têm nomes próprios (`syncrofin-enterprise-*`, `charts-enterprise`): uma tag aqui não mexe nas da Community.
- Trabalhe em branch e abra PR; o plano de trabalho é `docs/ENTERPRISE.md`.

## App Android (`mobile/`)

Capacitor 8 + React 19, projeto próprio (`mobile/README.md`). `npm install --legacy-peer-deps` (o npm 11 falha ao resolver os
peers opcionais do vitest). Testes: `npm test`; APK: `npm run apk:debug` (precisa de JDK 21 e Android SDK 36). Keystore de
release **nunca** vai para o git. Verificado num Galaxy A55 (Android 16): login, 2FA, Keystore, câmera e upload nativo
(`mobile/README.md`); teste pelo cabo com `adb reverse tcp:8100 tcp:8100` e o APK de debug (aceita HTTP só para localhost).

## Stack e comandos

- Backend `backend/`: FastAPI + SQLAlchemy async + Alembic + Celery; Postgres (pgvector) + Redis.
- Frontend `frontend/`: React 19 + TS + Vite + Tailwind 4 + TanStack Query + i18next.
- Stack completa: `docker compose up --build` (front :3100, API :8100/api/docs).
- Backend (precisa de **PostgreSQL real**; sem fallback SQLite): `docker compose -f docker-compose.test.yml up -d`
  e então `cd backend && pytest -n 4` · `ruff check .` · `ty check .` · `python scripts/check_migration_chain.py`
- Frontend: `cd frontend && npm run typecheck && npm run lint && npm test`
- Lock do backend: `backend/scripts/lock.sh` (sempre commitar `uv.lock` junto do `pyproject.toml`).

## Regras do projeto

- Regra de negócio em `services/`; rotas (`api/`) finas; toda entidade financeira tem `workspace_id`.
- Migrações Alembic com numeração sequencial (próxima: `093_…`); uma única cabeça.
- Dinheiro é `Decimal`; `type='debit'` = despesa, `'credit'` = receita.
- Textos de UI via i18n (`frontend/src/locales/*.json`, ao menos `en` e `pt-BR`).
- Comentários explicam o *porquê*, como no código existente.
- Commits em Conventional Commits. Nunca commitar `.env`, `secrets/`, `backend/data/`.

## Armadilhas conhecidas

- **Licença:** o código herdado é AGPL-3.0 de terceiros. Não remova `LICENSE` nem avisos, nem declare outra
  licença sobre ele (ele é AGPL-3.0 de terceiros). Posicionamento: gestão financeira + exportação para o
  contador; **não** partidas dobradas.
- Idiomas: só `en`, `pt-BR` e `es`. Chave de i18n nova → **os três** (a suíte exige paridade); `npm run i18n:check -- --strict`.
- Testes rodam em Postgres com chaves estrangeiras reais: crie as linhas-pai; sem relacionamento ORM, `flush()` a pai antes da filha.
- E-mail (reset/convites): host dos links vem de `FRONTEND_URL`; envio de reset é em *background* (não revela quem tem conta).
- Tela/rota nova → também um tópico em `frontend/src/help/topics.ts` (o botão **?** abre a página da tela; `topics.test.ts` falha
  se faltar). Manual em `frontend/src/help/content/pt-BR/*.md`; depois de editar, `npm run manual:build` (gera `docs/MANUAL.md`).
- Toda rota mutante nova precisa de decisão de permissão ou entrada na `ALLOWLIST` de
  `backend/tests/test_write_permission_coverage.py`.
- Testes que criam objetos na sessão e chamam serviços que usam relacionamentos lazy: use
  `session.expunge_all()` antes (ver `test_reconciliation_auto_apply.py`).
- O service worker (`frontend/public/sw.js`) **nunca** pode guardar `/api/*`.
- **Não renomeie** os identificadores `securo-*` listados em `docs/ARCHITECTURE.md` §8 (salt de
  criptografia, servidor MCP `securo`, JWT iss/aud, `securo-chart`, formatos de export): estão
  persistidos em dados/arquivos.
- Variável de ambiente nova precisa ser declarada em `x-backend-env` dos compose para chegar ao container.
- `docker-compose.prod.yml`/`install.sh`/Helm usam imagens `ghcr.io/gustavoflandal/syncrofin-enterprise-*` (chart em
  `charts-enterprise`), publicadas ao enviar uma tag `vX.Y.Z`. **Privadas: não as torne públicas** (`docker login ghcr.io`;
  Helm: `imagePullSecrets`). Ver `docs/DEPLOYMENT.md`.
