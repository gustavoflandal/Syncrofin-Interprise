import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.audit import seal
from app.core.config import get_settings
from app.services import access_log_service
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _seal() -> int:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession)() as session:
            return await seal(session)
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.audit_tasks.seal_audit_events")
def seal_audit_events() -> int:
    """Chain the audit events written since the last run."""
    sealed = asyncio.run(_seal())
    if sealed:
        logger.info("Audit trail: sealed %d events", sealed)
    return sealed


async def _purge() -> int:
    engine = create_async_engine(get_settings().database_url)
    try:
        async with async_sessionmaker(engine, class_=AsyncSession)() as session:
            return await access_log_service.purge_expired(session)
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.audit_tasks.purge_access_log")
def purge_access_log() -> int:
    """Anonymise the access records whose retention period is over."""
    purged = asyncio.run(_purge())
    if purged:
        logger.info("Access log: anonymised %d events", purged)
    return purged
