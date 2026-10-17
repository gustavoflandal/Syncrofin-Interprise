import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.data_retention import DataRetentionPolicy
from app.services import data_retention_service
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _purge_all() -> dict:
    engine = create_async_engine(get_settings().database_url)
    try:
        SessionLocal = async_sessionmaker(engine, class_=AsyncSession)
        async with SessionLocal() as session:
            result = await session.execute(select(DataRetentionPolicy.workspace_id))
            workspace_ids = [row[0] for row in result.all()]

        totals = {"transactions_anonymized": 0, "attachments_deleted": 0, "audit_anonymized": 0}
        for ws_id in workspace_ids:
            async with SessionLocal() as session:
                try:
                    counts = await data_retention_service.purge_expired_data(session, ws_id)
                    await session.commit()
                    for key in totals:
                        totals[key] += counts[key]
                except Exception:
                    logger.exception("Retention purge failed for workspace %s", ws_id)
        return totals
    finally:
        await engine.dispose()


@celery_app.task(name="purge-expired-data", max_retries=2, retry_backoff=True)
def purge_expired_data():
    """Run data retention purge for all workspaces that have policies."""
    totals = asyncio.run(_purge_all())
    total = sum(totals.values())
    if total:
        logger.info("Retention purge complete: %s", totals)
    return totals
