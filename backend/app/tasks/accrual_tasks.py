import asyncio
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.models.accrual_schedule import AccrualSchedule
from app.services import accrual_service
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _post_all() -> dict:
    engine = create_async_engine(get_settings().database_url)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    posted = skipped = 0
    try:
        async with session_maker() as session:
            result = await session.execute(
                select(AccrualSchedule.workspace_id).where(AccrualSchedule.is_active.is_(True)).distinct()
            )
            workspace_ids = [row[0] for row in result.all()]

        for workspace_id in workspace_ids:
            try:
                async with session_maker() as session:
                    summary = await accrual_service.post_entries(session, workspace_id, date.today())
                    posted += summary["posted"]
                    skipped += summary["skipped"]
            except Exception:
                logger.exception("Failed to post accrual entries for workspace %s", workspace_id)
    finally:
        await engine.dispose()
    return {"posted": posted, "skipped": skipped}


@celery_app.task(
    name="app.tasks.accrual_tasks.post_due_accruals",
    max_retries=2,
    retry_backoff=True,
)
def post_due_accruals() -> dict:
    """Celery task: lança as parcelas de provisão/diferimento vencidas em todos os workspaces.

    Idempotente: parcelas já lançadas não voltam a ser selecionadas.
    """
    summary = asyncio.run(_post_all())
    logger.info("Accrual posting complete: %s", summary)
    return summary
