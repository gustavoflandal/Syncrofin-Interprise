# SyncroFin Enterprise — API Changelog

Este documento registra alterações na **API pública versionada** (`/api/v1`).
Os endpoints internos em `/api/` são usados pelo frontend e podem mudar sem aviso;
a camada `/api/v1` segue [Semantic Versioning](https://semver.org/) e promete:

- **Sem remoção de campo ou de endpoint** sem passar por um período de deprecação de
  no mínimo **90 dias**.
- **Sem mudança de tipo** em campos existentes (string→int, por exemplo).
- **Novos campos** podem ser adicionados a qualquer momento sem aviso prévio; trate
  respostas desconhecidas com permissividade (ignore campos extras).

## Autenticação

Bearer token obtido em **Configurações → Tokens de API**.

```
Authorization: Bearer <token>
X-Workspace-Id: <workspace_id>   # necessário em todos os endpoints de workspace
```

## Paginação

Todos os endpoints que retornam listas paginadas usam:

| Parâmetro | Tipo    | Padrão | Máximo |
|-----------|---------|--------|--------|
| `page`    | inteiro | 1      | —      |
| `limit`   | inteiro | 50     | 200    |

Resposta:

```json
{
  "items": [...],
  "total": 1024,
  "page": 1,
  "limit": 50
}
```

## Recursos estáveis

| Método | Caminho | Descrição |
|--------|---------|-----------|
| GET | `/api/v1/info` | Metadados e versão da API |
| GET | `/api/v1/workspaces` | Lista workspaces do usuário |
| GET | `/api/v1/workspaces/{id}` | Detalhes de um workspace |
| GET | `/api/v1/workspaces/{id}/accounts` | Lista contas |
| GET | `/api/v1/workspaces/{id}/transactions` | Lista transações (paginado) |
| GET | `/api/v1/workspaces/{id}/invoices` | Lista faturas (paginado) |
| GET | `/api/v1/workspaces/{id}/payees` | Lista favorecidos |
| GET | `/api/v1/workspaces/{id}/categories` | Lista categorias |

OpenAPI interativo: `GET /api/v1/docs`

---

## v1.0.0 — 2026-10-06

**Lançamento inicial da API pública.**

Recursos incluídos: workspaces, accounts, transactions, invoices, payees, categories.
