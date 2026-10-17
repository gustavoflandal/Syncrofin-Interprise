"""Sincronização com ERP em segundo plano (F3).

A rota só enfileira; o trabalho (que fala com uma API externa limitada a ~3 req/s) roda aqui,
fora do ciclo da requisição.
"""
import asyncio
import logging
import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.services import erp_service
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _run(
    connection_id: str, entity_type: str, date_from: str | None, date_to: str | None
) -> dict:
    engine = create_async_engine(get_settings().database_url)
    try:
        session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with session_maker() as session:
            run = await erp_service.run_sync(
                session,
                uuid.UUID(connection_id),
                entity_type,
                date.fromisoformat(date_from) if date_from else None,
                date.fromisoformat(date_to) if date_to else None,
            )
            summary = {
                "status": run.status,
                "created": run.created_count,
                "updated": run.updated_count,
                "errors": run.error_count,
            }
            await session.commit()
            return summary
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.erp_tasks.sync_erp_connection")
def sync_erp_connection(
    connection_id: str,
    entity_type: str,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """Roda uma sincronização de ERP. Falhas ficam no `ErpSyncRun`, não relançam (sem retry cego
    de uma operação que pode já ter gravado no ERP)."""
    summary = asyncio.run(_run(connection_id, entity_type, date_from, date_to))
    logger.info("ERP sync %s (%s): %s", connection_id, entity_type, summary)
    return summary
