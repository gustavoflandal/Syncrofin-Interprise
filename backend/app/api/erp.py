"""API de conectores ERP (F3).

  GET    /api/erp/providers
  POST   /api/erp/connections
  GET    /api/erp/connections
  GET    /api/erp/connections/{id}
  PATCH  /api/erp/connections/{id}
  DELETE /api/erp/connections/{id}
  POST   /api/erp/connections/{id}/test
  POST   /api/erp/connections/{id}/sync      (enfileira a task Celery; responde 202)
  GET    /api/erp/connections/{id}/history
  GET    /api/erp/connections/{id}/mappings

O workspace vem de `X-Workspace-Id` (como no resto da API). Credenciais nunca são devolvidas.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, require_permission
from app.erp import available_connectors
from app.models.erp_connection import ENTITY_TYPES, SUPPORTED_ERP_PROVIDERS, ErpConnection
from app.schemas.erp import (
    ErpConnectionCreate,
    ErpConnectionRead,
    ErpConnectionUpdate,
    ErpMappingRead,
    ErpProviderRead,
    ErpSyncQueued,
    ErpSyncRequest,
    ErpSyncRunRead,
    ErpTestResult,
)
from app.services import erp_service

_read_gate = require_permission("erp.read")
_manage_gate = require_permission("erp.manage")

router = APIRouter(prefix="/api/erp", tags=["erp"])

#: Registrados mas sem implementação — aparecem na lista para a UI, com `available=False`.
_COMING_SOON = frozenset({"contaazul"})


async def _get(
    session: AsyncSession, ctx: WorkspaceContext, connection_id: uuid.UUID
) -> ErpConnection:
    try:
        return await erp_service.get_connection(session, ctx.id, connection_id)
    except erp_service.ErpConnectionNotFound:
        raise HTTPException(status_code=404, detail="Conexão ERP não encontrada")


@router.get("/providers", response_model=list[ErpProviderRead])
async def list_providers(ctx: WorkspaceContext = Depends(_read_gate)):
    return [
        ErpProviderRead(key=k, available=k not in _COMING_SOON)
        for k in available_connectors()
        if k in SUPPORTED_ERP_PROVIDERS
    ]


@router.post("/connections", response_model=ErpConnectionRead, status_code=201)
async def create_connection(
    data: ErpConnectionCreate,
    ctx: WorkspaceContext = Depends(_manage_gate),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        conn = await erp_service.create_connection(
            session,
            ctx.id,
            data.provider,
            data.credentials,
            data.sync_config,
            created_by_user_id=ctx.user_id,
        )
    except erp_service.ErpServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await session.commit()
    await session.refresh(conn)
    return conn


@router.get("/connections", response_model=list[ErpConnectionRead])
async def list_connections(
    ctx: WorkspaceContext = Depends(_read_gate),
    session: AsyncSession = Depends(get_async_session),
):
    return await erp_service.list_connections(session, ctx.id)


@router.get("/connections/{connection_id}", response_model=ErpConnectionRead)
async def get_connection(
    connection_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_read_gate),
    session: AsyncSession = Depends(get_async_session),
):
    return await _get(session, ctx, connection_id)


@router.patch("/connections/{connection_id}", response_model=ErpConnectionRead)
async def update_connection(
    connection_id: uuid.UUID,
    data: ErpConnectionUpdate,
    ctx: WorkspaceContext = Depends(_manage_gate),
    session: AsyncSession = Depends(get_async_session),
):
    conn = await _get(session, ctx, connection_id)
    try:
        await erp_service.update_connection(
            session,
            conn,
            credentials=data.credentials,
            config=data.sync_config,
            is_active=data.is_active,
        )
    except erp_service.ErpServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await session.commit()
    await session.refresh(conn)
    return conn


@router.delete("/connections/{connection_id}", status_code=204)
async def delete_connection(
    connection_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_manage_gate),
    session: AsyncSession = Depends(get_async_session),
):
    conn = await _get(session, ctx, connection_id)
    await erp_service.delete_connection(session, conn)
    await session.commit()


@router.post("/connections/{connection_id}/test", response_model=ErpTestResult)
async def test_connection(
    connection_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_manage_gate),
    session: AsyncSession = Depends(get_async_session),
):
    await _get(session, ctx, connection_id)
    return ErpTestResult(**await erp_service.test_connection(session, connection_id))


@router.post("/connections/{connection_id}/sync", response_model=ErpSyncQueued, status_code=202)
async def trigger_sync(
    connection_id: uuid.UUID,
    data: ErpSyncRequest,
    ctx: WorkspaceContext = Depends(_manage_gate),
    session: AsyncSession = Depends(get_async_session),
):
    conn = await _get(session, ctx, connection_id)
    if data.entity_type not in ENTITY_TYPES:
        raise HTTPException(status_code=422, detail="entity_type inválido")
    direction = erp_service.ENTITY_DIRECTION[data.entity_type]
    if data.direction and data.direction != direction:
        raise HTTPException(
            status_code=422,
            detail=f"{data.entity_type} só sincroniza no sentido {direction}",
        )
    if not conn.is_active:
        raise HTTPException(status_code=409, detail="Conexão desativada")

    conn.last_sync_status = "running"
    await session.commit()

    # Import tardio: a task importa o app Celery, que não deve ser carregado só para servir rotas.
    from app.tasks.erp_tasks import sync_erp_connection

    sync_erp_connection.delay(
        str(conn.id),
        data.entity_type,
        data.date_from.isoformat() if data.date_from else None,
        data.date_to.isoformat() if data.date_to else None,
    )
    return ErpSyncQueued(entity_type=data.entity_type, direction=direction)


@router.get("/connections/{connection_id}/history", response_model=list[ErpSyncRunRead])
async def sync_history(
    connection_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    ctx: WorkspaceContext = Depends(_read_gate),
    session: AsyncSession = Depends(get_async_session),
):
    await _get(session, ctx, connection_id)
    return await erp_service.get_sync_history(session, connection_id, limit)


@router.get("/connections/{connection_id}/mappings", response_model=list[ErpMappingRead])
async def mappings(
    connection_id: uuid.UUID,
    entity_type: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    ctx: WorkspaceContext = Depends(_read_gate),
    session: AsyncSession = Depends(get_async_session),
):
    await _get(session, ctx, connection_id)
    return await erp_service.list_mappings(session, connection_id, entity_type, limit)
