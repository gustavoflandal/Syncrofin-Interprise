"""Serviço de conectores ERP (F3).

Fluxo:
  1. `create_connection`  — guarda as credenciais cifradas (JSON) e a configuração de sync.
  2. `sync_*` / `push_*`  — cada execução grava um `ErpSyncRun` e atualiza o resumo na conexão.
  3. `erp_entity_mappings` — liga id local a id externo; é isso que torna o pull idempotente
     (a segunda execução atualiza, não duplica) e o push incremental (o que já foi não vai de novo).

Regras que valem a pena preservar:
  - Credenciais nunca saem daqui em claro: a API só diz *se* existem.
  - Um item que falha não derruba o lote: cada item roda num savepoint, o erro vai para o run.
  - Falha da execução inteira (rede, credencial) é registrada no run e na conexão, e o savepoint
    externo desfaz o que ela tivesse feito pela metade, mas o registro da tentativa permanece.
  - Os serviços fazem `flush`, nunca `commit`: quem chama (rota ou task Celery) fecha a transação.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_value, encrypt_value
from app.erp import ErpConnector, ErpError, get_connector
from app.erp.base import ErpInvoice, ErpTransaction, SyncResult
from app.erp.registry import available_connectors
from app.fiscal.registry import TaxIdKind, normalise_and_validate
from app.models.category import Category
from app.models.erp_connection import (
    ENTITY_TYPES,
    SUPPORTED_ERP_PROVIDERS,
    ErpConnection,
    ErpEntityMapping,
    ErpSyncRun,
)
from app.models.invoice import Invoice
from app.models.payee import Payee, PayeeTaxId
from app.models.transaction import Transaction
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

#: Opções de sync_config repassadas ao conector (não são segredos).
CONNECTOR_OPTION_KEYS = ("default_category_code", "default_account_id")
#: Direção fixa de cada tipo de entidade: o ERP é a fonte de plano de contas e cadastros, o
#: SyncroFin é a fonte de lançamentos e faturas.
ENTITY_DIRECTION = {
    "category": "pull",
    "payee": "pull",
    "transaction": "push",
    "invoice": "push",
}
MAX_ERRORS_STORED = 50


class ErpServiceError(Exception):
    """Pedido inválido (provedor desconhecido, credencial incompleta, tipo de sync errado)."""


class ErpConnectionNotFound(Exception):
    pass


# ────────────────────────────────────────────────────────────────────────────
# Conexões
# ────────────────────────────────────────────────────────────────────────────

def _validate_credentials(provider: str, credentials: dict[str, Any]) -> None:
    if provider == "omie":
        if not credentials.get("app_key") or not credentials.get("app_secret"):
            raise ErpServiceError("Omie exige app_key e app_secret")


async def create_connection(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    provider: str,
    credentials: dict[str, Any],
    config: Optional[dict[str, Any]] = None,
    created_by_user_id: Optional[uuid.UUID] = None,
) -> ErpConnection:
    if provider not in SUPPORTED_ERP_PROVIDERS or provider not in available_connectors():
        raise ErpServiceError(f"Provedor ERP inválido: {provider}")
    _validate_credentials(provider, credentials)
    conn = ErpConnection(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        created_by_user_id=created_by_user_id,
        provider=provider,
        credentials_enc=encrypt_value(json.dumps(credentials)),
        is_active=True,
        sync_config=dict(config or {}),
    )
    session.add(conn)
    await session.flush()
    return conn


async def get_connection(
    session: AsyncSession, workspace_id: uuid.UUID, connection_id: uuid.UUID
) -> ErpConnection:
    conn = await session.get(ErpConnection, connection_id)
    if conn is None or conn.workspace_id != workspace_id:
        raise ErpConnectionNotFound()
    return conn


async def list_connections(session: AsyncSession, workspace_id: uuid.UUID) -> list[ErpConnection]:
    result = await session.execute(
        select(ErpConnection)
        .where(ErpConnection.workspace_id == workspace_id)
        .order_by(ErpConnection.created_at)
    )
    return list(result.scalars())


async def update_connection(
    session: AsyncSession,
    conn: ErpConnection,
    *,
    credentials: Optional[dict[str, Any]] = None,
    config: Optional[dict[str, Any]] = None,
    is_active: Optional[bool] = None,
) -> ErpConnection:
    if credentials is not None:
        _validate_credentials(conn.provider, credentials)
        conn.credentials_enc = encrypt_value(json.dumps(credentials))
    if config is not None:
        conn.sync_config = dict(config)
    if is_active is not None:
        conn.is_active = is_active
    await session.flush()
    return conn


async def delete_connection(session: AsyncSession, conn: ErpConnection) -> None:
    # Mapeamentos e execuções saem junto (ON DELETE CASCADE); as entidades locais ficam.
    await session.delete(conn)
    await session.flush()


def read_credentials(conn: ErpConnection) -> dict[str, Any]:
    raw = decrypt_value(conn.credentials_enc)
    if not raw:
        raise ErpServiceError("Credenciais ilegíveis (SECRET_KEY mudou?); informe-as novamente")
    return json.loads(raw)


def build_connector(conn: ErpConnection) -> ErpConnector:
    """Instancia o conector da conexão. Ponto único, para os testes substituírem."""
    options = {
        k: v for k, v in (conn.sync_config or {}).items() if k in CONNECTOR_OPTION_KEYS
    }
    return get_connector(conn.provider, **read_credentials(conn), **options)


async def _load(session: AsyncSession, connection_id: uuid.UUID) -> ErpConnection:
    conn = await session.get(ErpConnection, connection_id)
    if conn is None:
        raise ErpConnectionNotFound()
    return conn


async def test_connection(session: AsyncSession, connection_id: uuid.UUID) -> dict[str, Any]:
    conn = await _load(session, connection_id)
    try:
        connector = build_connector(conn)
        ok = await connector.test_connection()
        message = getattr(connector, "last_message", None)
    except (ErpError, ErpServiceError) as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": bool(ok), "message": None if ok else message}


# ────────────────────────────────────────────────────────────────────────────
# Mapeamentos
# ────────────────────────────────────────────────────────────────────────────

async def get_mapping_by_external(
    session: AsyncSession, connection_id: uuid.UUID, entity_type: str, external_id: str
) -> Optional[ErpEntityMapping]:
    return (
        await session.execute(
            select(ErpEntityMapping).where(
                ErpEntityMapping.connection_id == connection_id,
                ErpEntityMapping.entity_type == entity_type,
                ErpEntityMapping.external_id == external_id,
            )
        )
    ).scalar_one_or_none()


async def get_mapping_by_local(
    session: AsyncSession, connection_id: uuid.UUID, entity_type: str, local_id: uuid.UUID
) -> Optional[ErpEntityMapping]:
    return (
        await session.execute(
            select(ErpEntityMapping).where(
                ErpEntityMapping.connection_id == connection_id,
                ErpEntityMapping.entity_type == entity_type,
                ErpEntityMapping.local_id == local_id,
            )
        )
    ).scalar_one_or_none()


async def link_entity(
    session: AsyncSession,
    conn: ErpConnection,
    entity_type: str,
    local_id: uuid.UUID,
    external_id: str,
) -> ErpEntityMapping:
    """Cria o mapeamento ou devolve o existente (idempotente)."""
    if entity_type not in ENTITY_TYPES:
        raise ErpServiceError(f"Tipo de entidade inválido: {entity_type}")
    existing = await get_mapping_by_external(session, conn.id, entity_type, external_id)
    if existing is not None:
        if existing.local_id != local_id:
            existing.local_id = local_id
            await session.flush()
        return existing
    mapping = ErpEntityMapping(
        id=uuid.uuid4(),
        workspace_id=conn.workspace_id,
        connection_id=conn.id,
        entity_type=entity_type,
        local_id=local_id,
        external_id=external_id,
    )
    session.add(mapping)
    await session.flush()
    return mapping


async def list_mappings(
    session: AsyncSession,
    connection_id: uuid.UUID,
    entity_type: Optional[str] = None,
    limit: int = 500,
) -> list[ErpEntityMapping]:
    stmt = select(ErpEntityMapping).where(ErpEntityMapping.connection_id == connection_id)
    if entity_type:
        stmt = stmt.where(ErpEntityMapping.entity_type == entity_type)
    stmt = stmt.order_by(ErpEntityMapping.entity_type, ErpEntityMapping.external_id).limit(limit)
    return list((await session.execute(stmt)).scalars())


# ────────────────────────────────────────────────────────────────────────────
# Execuções
# ────────────────────────────────────────────────────────────────────────────

async def get_sync_history(
    session: AsyncSession, connection_id: uuid.UUID, limit: int = 50
) -> list[ErpSyncRun]:
    result = await session.execute(
        select(ErpSyncRun)
        .where(ErpSyncRun.connection_id == connection_id)
        .order_by(ErpSyncRun.started_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def _execute(
    session: AsyncSession,
    conn: ErpConnection,
    entity_type: str,
    work: Callable[[ErpConnector], Awaitable[SyncResult]],
) -> ErpSyncRun:
    direction = ENTITY_DIRECTION[entity_type]
    run = ErpSyncRun(
        id=uuid.uuid4(),
        connection_id=conn.id,
        workspace_id=conn.workspace_id,
        started_at=datetime.now(timezone.utc),
        status="running",
        entity_type=entity_type,
        direction=direction,
    )
    session.add(run)
    conn.last_sync_status = "running"
    conn.last_sync_error = None
    await session.flush()

    result: Optional[SyncResult] = None
    failure: Optional[str] = None
    try:
        # Savepoint: se a execução falhar no meio, o que ela gravou é desfeito, mas o `run` não.
        async with session.begin_nested():
            result = await work(build_connector(conn))
    except NotImplementedError as exc:
        failure = str(exc) or "Não implementado por este conector"
    except (ErpError, ErpServiceError) as exc:
        failure = str(exc)
    except Exception as exc:  # noqa: BLE001 — qualquer falha vira registro, não 500 numa task
        logger.exception("ERP sync %s/%s failed for connection %s", entity_type, direction, conn.id)
        failure = f"{type(exc).__name__}: {exc}"

    errors = list(result.errors) if result else []
    if failure:
        errors.insert(0, failure)
    run.created_count = result.created if result else 0
    run.updated_count = result.updated if result else 0
    run.error_count = len(errors)
    run.errors = errors[:MAX_ERRORS_STORED]
    nothing_worked = errors and not (run.created_count or run.updated_count)
    run.status = "error" if (failure or nothing_worked) else "success"
    run.finished_at = datetime.now(timezone.utc)

    conn.last_sync_at = run.finished_at
    conn.last_sync_status = run.status
    conn.last_sync_error = errors[0][:2000] if errors else None
    await session.flush()
    return run


# ────────────────────────────────────────────────────────────────────────────
# Pull: plano de contas e beneficiários
# ────────────────────────────────────────────────────────────────────────────

async def _owner_user_id(session: AsyncSession, conn: ErpConnection) -> uuid.UUID:
    if conn.created_by_user_id:
        return conn.created_by_user_id
    ws = await session.get(Workspace, conn.workspace_id)
    if ws is not None and ws.created_by_user_id:
        return ws.created_by_user_id
    raise ErpServiceError("Conexão sem usuário responsável para atribuir os registros importados")


async def sync_chart_of_accounts(session: AsyncSession, connection_id: uuid.UUID) -> ErpSyncRun:
    conn = await _load(session, connection_id)

    async def work(connector: ErpConnector) -> SyncResult:
        user_id = await _owner_user_id(session, conn)
        result = SyncResult()
        for acc in await connector.pull_chart_of_accounts():
            name = acc.name.strip()[:100]
            try:
                async with session.begin_nested():
                    mapping = await get_mapping_by_external(
                        session, conn.id, "category", acc.external_id
                    )
                    category = await session.get(Category, mapping.local_id) if mapping else None
                    if category is not None:
                        if category.name != name:
                            category.name = name
                            result.updated += 1
                        else:
                            result.skipped += 1
                        continue
                    # Sem mapeamento (ou categoria apagada): reaproveita uma de mesmo nome em vez
                    # de duplicar o que o usuário já tinha criado à mão.
                    category = (
                        await session.execute(
                            select(Category)
                            .where(
                                Category.workspace_id == conn.workspace_id,
                                func.lower(Category.name) == name.lower(),
                            )
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                    if category is None:
                        category = Category(
                            id=uuid.uuid4(),
                            user_id=user_id,
                            workspace_id=conn.workspace_id,
                            name=name,
                        )
                        session.add(category)
                        await session.flush()
                        result.created += 1
                    else:
                        result.skipped += 1
                    if mapping is not None:
                        mapping.local_id = category.id
                    else:
                        await link_entity(session, conn, "category", category.id, acc.external_id)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{acc.external_id}: {exc}")
        return result

    return await _execute(session, conn, "category", work)


async def _apply_tax_id(
    session: AsyncSession, payee: Payee, tax_id: Optional[str], tax_id_type: Optional[str]
) -> None:
    if not tax_id or tax_id_type not in ("cpf", "cnpj"):
        return
    kind = TaxIdKind(tax_id_type)
    value, error = normalise_and_validate(kind, tax_id)
    if error:
        return  # documento inválido no ERP: não polui o cadastro, o nome já identifica
    exists = (
        await session.execute(
            select(PayeeTaxId.id).where(PayeeTaxId.payee_id == payee.id, PayeeTaxId.kind == kind.value)
        )
    ).first()
    if exists is None:
        session.add(
            PayeeTaxId(
                id=uuid.uuid4(),
                payee_id=payee.id,
                workspace_id=payee.workspace_id,
                kind=kind.value,
                value=value,
            )
        )
        await session.flush()


async def sync_payees(session: AsyncSession, connection_id: uuid.UUID) -> ErpSyncRun:
    conn = await _load(session, connection_id)

    async def work(connector: ErpConnector) -> SyncResult:
        user_id = await _owner_user_id(session, conn)
        result = SyncResult()
        for ext in await connector.pull_payees():
            name = ext.name.strip()[:255]
            try:
                async with session.begin_nested():
                    mapping = await get_mapping_by_external(session, conn.id, "payee", ext.external_id)
                    payee = await session.get(Payee, mapping.local_id) if mapping else None
                    if payee is not None:
                        if payee.name != name:
                            payee.name = name
                            result.updated += 1
                        else:
                            result.skipped += 1
                        await _apply_tax_id(session, payee, ext.tax_id, ext.tax_id_type)
                        continue
                    payee = (
                        await session.execute(
                            select(Payee)
                            .where(
                                Payee.workspace_id == conn.workspace_id,
                                func.lower(func.trim(Payee.name)) == name.lower(),
                            )
                            .limit(1)
                        )
                    ).scalar_one_or_none()
                    if payee is None:
                        payee = Payee(
                            id=uuid.uuid4(),
                            user_id=user_id,
                            workspace_id=conn.workspace_id,
                            name=name,
                            type={"cnpj": "company", "cpf": "person"}.get(ext.tax_id_type or ""),
                            source="erp",
                        )
                        session.add(payee)
                        await session.flush()
                        result.created += 1
                    else:
                        result.skipped += 1
                    if mapping is not None:
                        mapping.local_id = payee.id
                    else:
                        await link_entity(session, conn, "payee", payee.id, ext.external_id)
                    await _apply_tax_id(session, payee, ext.tax_id, ext.tax_id_type)
            except Exception as exc:  # noqa: BLE001
                result.errors.append(f"{ext.external_id}: {exc}")
        return result

    return await _execute(session, conn, "payee", work)


# ────────────────────────────────────────────────────────────────────────────
# Push: lançamentos e faturas
# ────────────────────────────────────────────────────────────────────────────

async def _already_pushed(
    session: AsyncSession, connection_id: uuid.UUID, entity_type: str
) -> set[uuid.UUID]:
    rows = await session.execute(
        select(ErpEntityMapping.local_id).where(
            ErpEntityMapping.connection_id == connection_id,
            ErpEntityMapping.entity_type == entity_type,
        )
    )
    return {r[0] for r in rows}


async def _external_for(
    session: AsyncSession,
    connection_id: uuid.UUID,
    entity_type: str,
    local_id: Optional[uuid.UUID],
) -> Optional[str]:
    if local_id is None:
        return None
    m = await get_mapping_by_local(session, connection_id, entity_type, local_id)
    return m.external_id if m else None


async def _record_pushed(
    session: AsyncSession, conn: ErpConnection, entity_type: str, result: SyncResult
) -> None:
    for ext_id in result.synced_external_ids:
        await link_entity(session, conn, entity_type, uuid.UUID(ext_id), ext_id)


async def push_transactions(
    session: AsyncSession,
    connection_id: uuid.UUID,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> ErpSyncRun:
    conn = await _load(session, connection_id)

    async def work(connector: ErpConnector) -> SyncResult:
        stmt = select(Transaction).where(Transaction.workspace_id == conn.workspace_id)
        if date_from:
            stmt = stmt.where(Transaction.date >= date_from)
        if date_to:
            stmt = stmt.where(Transaction.date <= date_to)
        done = await _already_pushed(session, conn.id, "transaction")
        batch: list[ErpTransaction] = []
        for tx in (await session.execute(stmt.order_by(Transaction.date))).scalars():
            if tx.id in done:
                continue
            batch.append(
                ErpTransaction(
                    external_id=str(tx.id),
                    date=tx.date,
                    amount=abs(tx.amount),
                    type=tx.type,
                    description=tx.description,
                    payee_external_id=await _external_for(session, conn.id, "payee", tx.payee_id),
                    category_code=await _external_for(session, conn.id, "category", tx.category_id),
                )
            )
        result = await connector.push_transactions(batch) if batch else SyncResult()
        await _record_pushed(session, conn, "transaction", result)
        return result

    return await _execute(session, conn, "transaction", work)


async def push_invoices(
    session: AsyncSession,
    connection_id: uuid.UUID,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> ErpSyncRun:
    conn = await _load(session, connection_id)

    async def work(connector: ErpConnector) -> SyncResult:
        # Só faturas emitidas (`open`): rascunho ainda pode mudar e `void` não deve existir lá.
        stmt = select(Invoice).where(
            Invoice.workspace_id == conn.workspace_id, Invoice.status == "open"
        )
        if date_from:
            stmt = stmt.where(Invoice.due_date >= date_from)
        if date_to:
            stmt = stmt.where(Invoice.due_date <= date_to)
        done = await _already_pushed(session, conn.id, "invoice")
        batch: list[ErpInvoice] = []
        for inv in (await session.execute(stmt.order_by(Invoice.due_date))).scalars().unique():
            if inv.id in done:
                continue
            label = inv.external_number or (f"{inv.series or ''}{inv.number}" if inv.number else "")
            batch.append(
                ErpInvoice(
                    external_id=str(inv.id),
                    direction=inv.direction,
                    amount=inv.total,
                    due_date=inv.due_date,
                    payee_external_id=await _external_for(session, conn.id, "payee", inv.payee_id),
                    description=f"SyncroFin {label}".strip(),
                    status=inv.status,
                )
            )
        result = await connector.push_invoices(batch) if batch else SyncResult()
        await _record_pushed(session, conn, "invoice", result)
        return result

    return await _execute(session, conn, "invoice", work)


# ────────────────────────────────────────────────────────────────────────────
# Despacho (usado pela task Celery)
# ────────────────────────────────────────────────────────────────────────────

async def run_sync(
    session: AsyncSession,
    connection_id: uuid.UUID,
    entity_type: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> ErpSyncRun:
    if entity_type == "category":
        return await sync_chart_of_accounts(session, connection_id)
    if entity_type == "payee":
        return await sync_payees(session, connection_id)
    if entity_type == "transaction":
        return await push_transactions(session, connection_id, date_from, date_to)
    if entity_type == "invoice":
        return await push_invoices(session, connection_id, date_from, date_to)
    raise ErpServiceError(f"Tipo de sincronização inválido: {entity_type}")
