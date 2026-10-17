# Contribuindo com o SyncroFin Enterprise

Obrigado por querer ajudar. Este guia é o caminho mais curto entre "clonei o repositório" e "meu PR passa no CI".

## Ambiente

```bash
git clone https://github.com/gustavoflandal/syncrofin-enterprise.git && cd syncrofin-enterprise

# Stack de desenvolvimento (hot reload): front em :3100, API em :8100/api/docs
docker compose up --build

# Banco dos testes: PostgreSQL real com pgvector, descartável (porta 55433)
docker compose -f docker-compose.test.yml up -d
```

Detalhes (migrações, i18n, como adicionar uma funcionalidade) em [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Antes de abrir o PR

O CI roda exatamente isto; rode localmente para não descobrir depois:

```bash
# backend
cd backend
pytest -n 4
ruff check . && ty check . && python scripts/check_migration_chain.py

# frontend
cd ../frontend
npm run lint && npm run typecheck && npm run i18n:check -- --strict && npm test
```

## Regras que o CI e os testes cobram

- **Testes contra PostgreSQL real.** Não existe fallback para SQLite. Se o seu teste insere um `workspace_id` ou
  `connection_id` inventado, ele falha: crie a linha-pai.
- **Migrações:** numeração sequencial (`093_…`), uma única cabeça, e o modelo e a migração precisam concordar
  (`tests/test_migrations_postgres.py`). Mexeu no `pyproject.toml`? Rode `backend/scripts/lock.sh` e commite o `uv.lock`.
- **Rotas mutantes** (`POST/PATCH/PUT/DELETE`) precisam declarar uma decisão de permissão
  (`current_writable_workspace`) ou entrar, com o motivo, na `ALLOWLIST` de
  `backend/tests/test_write_permission_coverage.py`.
- **Textos de interface:** três idiomas (`en`, `pt-BR`, `es`). Chave nova vai nos três.
- **Variável de ambiente nova** precisa ser declarada em `x-backend-env` dos dois `docker-compose*.yml` (e no Helm,
  se for o caso) para chegar ao container.
- Nunca faça *commit* de `.env`, `secrets/` ou dados de `backend/data/`.

## Estilo

- Backend: async em tudo que toca o banco, `Decimal` para dinheiro, regra de negócio em `services/` (rotas finas).
- Comentários explicam o **porquê** — o código existente é assim; mantenha o padrão.
- Commits em [Conventional Commits](https://www.conventionalcommits.org/pt-br/) (`feat:`, `fix:`, `docs:`, `chore:`…).

## Segurança

Vulnerabilidade? **Não abra uma issue pública.** Use o [aviso de segurança privado](https://github.com/gustavoflandal/syncrofin-enterprise/security/advisories/new).
Veja também [SECURITY.md](SECURITY.md).

## Licença

Ao contribuir, você concorda que sua contribuição será distribuída sob a licença do projeto
([AGPL-3.0](LICENSE)).
