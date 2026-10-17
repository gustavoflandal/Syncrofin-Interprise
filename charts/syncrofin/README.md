# SyncroFin Helm Chart

[SyncroFin](https://github.com/gustavoflandal/SyncroFin) is an advanced, self-hosted personal finance manager with built-in AI agents. This Helm chart provides a complete, production-ready deployment of SyncroFin to any Kubernetes cluster.

## Features

- **Complete Application Stack**: Deploys the React (Vite) frontend, served by nginx, and the FastAPI backend, fully supporting all features including Open Banking integrations, OIDC authentication, and AI financial agents.
- **Asynchronous Task Scheduler**: Runs Celery workers and a Celery beat singleton for automated background processing (such as bank syncs, recurring transactions, and exchange rate updates).
- **Databases**: Easily configure connections to your external PostgreSQL and Redis instances.
- **Gateway API & Ingress**: Native support for standard Kubernetes Ingress or the modern Kubernetes Gateway API (`HTTPRoute`).

## Prerequisites

- Kubernetes 1.25+
- Helm 3.2.0+
- PostgreSQL 15+ (with the `pgvector` extension installed)
- Redis 7+
- Persistent Volume (PV) provisioner support in the underlying infrastructure

### Persistent Storage Requirements
Since the Backend, Celery Worker, and MCP Server all share the same files (like uploaded attachments and AI knowledge bases), they all mount the same Persistent Volume Claims concurrently.
**If your cluster spans multiple nodes, you MUST use a StorageClass that supports `ReadWriteMany` (RWX) access mode (e.g., NFS, CephFS, or Longhorn RWX).**
If your storage only supports `ReadWriteOnce` (RWO), you must restrict all SyncroFin pods to run on a single node (using `nodeSelector` or `podAffinity`) but that is an antipattern in Kubernetes.

## Required values (no defaults)

The example secrets that used to ship in `values.yaml` were public, so the chart no longer has defaults for them and
**refuses to render** without them (the error names the value and the command to generate it):

| Value | When | Generate |
|-------|------|----------|
| `secret.secretKey` | always (unless `global.existingSecret`) | `openssl rand -hex 32` |
| `postgresql.password` | while `postgresql.enabled` is true | `openssl rand -hex 24` (letters and digits: it goes inside a URL) |
| `secret.agentsMcpJwtSecret` | while `config.agentsEnabled` is `"true"` | `openssl rand -hex 32` |

```bash
helm install syncrofin ./charts/syncrofin \
  --set secret.secretKey=$(openssl rand -hex 32) \
  --set postgresql.password=$(openssl rand -hex 24)
```

The backend also refuses to start on the placeholder values from this repository, so a value copied from an old example
fails at startup with a clear message. Changing `postgresql.password` on a cluster that already has a database volume does
not change the database user: run `ALTER USER postgres PASSWORD '...'` inside the database first (see `docs/DEPLOYMENT.md`).

## Quickstart

If you want to install the latest official release from the GitHub Container Registry (GHCR):

```bash
helm install syncrofin oci://ghcr.io/gustavoflandal/charts/syncrofin --version <VERSION>
```

If you are developing locally and want to install from the source repository:

```bash
helm install syncrofin ./charts/syncrofin
```

## Configuration

All application-level features (such as AI Services, OIDC authentication, and Open Banking integrations) can be configured directly through Helm.
The keys in the `config:` and `secret:` blocks of the `values.yaml` map directly to the `UPPER_SNAKE_CASE` environment variables used in the standard Docker setup (converted to `camelCase`).

For a full list of available environment variables and API keys, please refer to the **[SyncroFin Application Configuration Guide](https://github.com/gustavoflandal/SyncroFin/tree/main/docs)**.

### Secrets Management (Production)

For production deployments, we highly recommend managing your secrets securely by passing an existing Kubernetes `Secret` rather than putting plain text keys in your `values.yaml`:

```yaml
global:
  existingSecret: "my-syncrofin-secrets"
```

The secret must contain the corresponding keys (e.g., `secretKey`, `databaseUrl`, `agentsOpenaiApiKey`).

## Uninstalling the Chart

To uninstall/delete the `syncrofin` deployment:

```bash
helm uninstall syncrofin
```

This command removes all the Kubernetes components associated with the chart and deletes the release. Note that Persistent Volume Claims (PVCs) created by the chart might not be deleted automatically to prevent accidental data loss.
