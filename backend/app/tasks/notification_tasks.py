import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.workspace import Workspace
from app.services import notification_delivery, notification_service
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _generate_all() -> dict:
    """Generate (and deliver) notifications for every active workspace."""
    engine = create_async_engine(get_settings().database_url)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    created_total = 0
    try:
        async with session_maker() as session:
            workspaces = (
                await session.execute(select(Workspace.id).where(Workspace.is_archived.is_(False)))
            ).all()
        for (workspace_id,) in workspaces:
            try:
                async with session_maker() as session:
                    workspace = await session.get(Workspace, workspace_id)
                    if workspace is None:  # deleted between listing and processing
                        continue
                    created = await notification_service.generate_for_workspace(session, workspace)
                    await notification_delivery.deliver(session, created)
                    await session.commit()
                    created_total += len(created)
            except Exception:
                logger.exception("Notification generation failed for workspace %s", workspace_id)
    finally:
        await engine.dispose()
    return {"created": created_total}


@celery_app.task(
    name="app.tasks.notification_tasks.generate_notifications",
    max_retries=2,
    retry_backoff=True,
)
def generate_notifications() -> dict:
    """Celery task: create budget / invoice / sync / forecast notifications."""
    result = asyncio.run(_generate_all())
    logger.info("Notification generation complete: %s", result)
    return result
