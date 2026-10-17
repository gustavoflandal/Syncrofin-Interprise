# Testes de Carga — SyncroFin Enterprise

Scripts k6 em `backend/scripts/k6/`. Medem p95 de latência nos endpoints críticos
com base de dados realista (≥ 100 k transações geradas por `seed_perf.py`).

## Pré-requisitos

```bash
# Instalar k6 (https://k6.io/docs/getting-started/installation/)
# macOS:   brew install k6
# Linux:   snap install k6
# Windows: choco install k6

# Iniciar a stack
docker compose up -d

# Seed de dados de performance (escala 10× → ~1 M de transações, ~15 min)
docker compose exec backend python scripts/seed_perf.py --scale 10
```

## Execução

```bash
cd backend/scripts/k6

# 1. Dashboard e listagens — 50 VUs, 2 min (meta: p95 < 500 ms)
k6 run dashboard.js

# 2. Relatórios DRE/DFC/AR-AP — 20 VUs, 2 min (meta: p95 < 2 s)
k6 run reports.js

# 3. Transações (leitura + escrita) — 30 VUs, 2 min (meta: p95 < 800 ms)
k6 run -e ACCOUNT_ID=<uuid-de-conta> transactions.js

# Contra ambiente remoto:
k6 run -e BASE_URL=https://app.example.com \
       -e EMAIL=loadtest@example.com \
       -e PASSWORD=SUA_SENHA \
       dashboard.js
```

## Metas de desempenho

| Cenário | VUs | p95 alvo |
|---------|-----|----------|
| Dashboard / listagens | 50 | < 500 ms |
| Relatórios (DRE/DFC) | 20 | < 2 000 ms |
| Transações mistas | 30 | < 800 ms |
| AR/AP overview | 20 | < 1 000 ms |

## Índices relevantes

Os índices críticos para os cenários acima estão em:

- `backend/alembic/versions/` — procure por `CREATE INDEX` nas migrações
- `Transaction`: índice em `(workspace_id, date DESC)`, `(account_id, date DESC)`
- `Invoice`: índice em `(workspace_id, direction, status, due_date)`
- `AuditLog`: índice em `(workspace_id, created_at DESC)`

Se um cenário não atingir a meta, use `EXPLAIN ANALYZE` na query lenta e adicione
o índice em uma nova migração Alembic.

## Interpretando resultados

k6 exibe um resumo ao final. Preste atenção em:

- `http_req_duration` → latência de ponta a ponta
- `http_req_failed` → deve ficar < 1 %
- `*_latency` → métricas customizadas por cenário (definidas em cada script)
