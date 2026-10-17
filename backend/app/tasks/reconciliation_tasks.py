import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.workspace import Workspace
from app.services import reconciliation_auto_service
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _auto_apply_all() -> dict:
    """Accept confident reconciliation suggestions in every workspace that opted in."""
    engine = create_async_engine(get_settings().database_url)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    applied = 0
    try:
        async with session_maker() as session:
            rows = (
                await session.execute(
                    select(Workspace.id).where(
                        Workspace.is_archived.is_(False),
                        Workspace.reconciliation_auto_apply_score.is_not(None),
                    )
                )
            ).all()
        for (workspace_id,) in rows:
            try:
                async with session_maker() as session:
                    workspace = await session.get(Workspace, workspace_id)
                    if workspace is None:  # deleted between listing and processing
                        continue
                    result = await reconciliation_auto_service.auto_apply(
                        session, workspace_id, workspace.reconciliation_auto_apply_score
                    )
                    await session.commit()
                    applied += result.applied
            except Exception:
                logger.exception("Reconciliation auto-apply failed for workspace %s", workspace_id)
    finally:
        await engine.dispose()
    return {"applied": applied}


@celery_app.task(name="app.tasks.reconciliation_tasks.auto_apply_suggestions")
def auto_apply_suggestions() -> dict:
    """Celery task: accept reconciliation suggestions that clear each workspace's bar."""
    result = asyncio.run(_auto_apply_all())
    logger.info("Reconciliation auto-apply complete: %s", result)
    return result
