"""Webhooks de saída por workspace — CRUD e endpoint de teste (F2).

Gated por ``workspace.manage`` (mesmo nível das configurações do workspace)
para criar/atualizar/deletar. Listagem usa ``export.read`` para que papéis
somente-leitura possam inspecionar os webhooks configurados.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, require_permission
from app.models.workspace_webhook import EVENT_TYPES
from app.schemas.webhook import WebhookCreate, WebhookRead, WebhookUpdate
from app.services import webhook_service

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

_read_gate = require_permission("export.read")
_manage_gate = require_permission("workspace.manage")


@router.get("", response_model=list[WebhookRead])
async def list_webhooks(
    ctx: WorkspaceContext = Depends(_read_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """Lista os webhooks configurados para o workspace."""
    whs = await webhook_service.list_webhooks(session, ctx.workspace.id)
    return [WebhookRead.from_orm(wh) for wh in whs]


@router.get("/event-types", response_model=list[str])
async def list_event_types(
    _ctx: WorkspaceContext = Depends(_read_gate),
):
    """Retorna os tipos de evento suportados."""
    return sorted(EVENT_TYPES)


@router.post("", response_model=WebhookRead, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    data: WebhookCreate,
    ctx: WorkspaceContext = Depends(_manage_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """Cria um novo webhook para o workspace."""
    wh = await webhook_service.create_webhook(session, ctx.workspace.id, ctx.user.id, data)
    await session.commit()
    return WebhookRead.from_orm(wh)


@router.get("/{webhook_id}", response_model=WebhookRead)
async def get_webhook(
    webhook_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_read_gate),
    session: AsyncSession = Depends(get_async_session),
):
    wh = await webhook_service.get_webhook(session, webhook_id, ctx.workspace.id)
    if not wh:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook não encontrado")
    return WebhookRead.from_orm(wh)


@router.put("/{webhook_id}", response_model=WebhookRead)
async def update_webhook(
    webhook_id: uuid.UUID,
    data: WebhookUpdate,
    ctx: WorkspaceContext = Depends(_manage_gate),
    session: AsyncSession = Depends(get_async_session),
):
    wh = await webhook_service.get_webhook(session, webhook_id, ctx.workspace.id)
    if not wh:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook não encontrado")
    wh = await webhook_service.update_webhook(session, wh, data)
    await session.commit()
    return WebhookRead.from_orm(wh)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_manage_gate),
    session: AsyncSession = Depends(get_async_session),
):
    wh = await webhook_service.get_webhook(session, webhook_id, ctx.workspace.id)
    if not wh:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook não encontrado")
    await webhook_service.delete_webhook(session, wh)
    await session.commit()


@router.post("/{webhook_id}/test", status_code=status.HTTP_200_OK)
async def test_webhook(
    webhook_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_manage_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """Envia um evento de teste para o endpoint configurado.

    Retorna imediatamente com ``{"scheduled": true}`` — a entrega é
    assíncrona e o resultado aparece em ``last_status_code`` após alguns
    segundos.
    """
    wh = await webhook_service.get_webhook(session, webhook_id, ctx.workspace.id)
    if not wh:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook não encontrado")
    webhook_service.dispatch(
        ctx.workspace.id,
        "transaction.created",   # evento de teste genérico
        {
            "test": True,
            "message": "Evento de teste do SyncroFin",
            "webhook_id": str(wh.id),
        },
        [wh],
    )
    return {"scheduled": True}
