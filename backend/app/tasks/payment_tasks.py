import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.services import payment_service
from app.worker import celery_app

logger = logging.getLogger(__name__)


async def _poll() -> int:
    engine = create_async_engine(get_settings().database_url)
    try:
        SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with SessionLocal() as session:
            return await payment_service.poll_sent_orders(session)
    finally:
        await engine.dispose()


@celery_app.task(name="app.tasks.payment_tasks.check_pending_payments", max_retries=2, retry_backoff=True)
def check_pending_payments():
    """Consulta o provedor para toda ordem de pagamento enviada e ainda não finalizada (F4).

    Idempotente: ordens já confirmadas/falhas/canceladas não são tocadas, e a
    criação do lançamento na confirmação só acontece uma vez por ordem.
    """
    changed = asyncio.run(_poll())
    if changed:
        logger.info("Payment status poll: %s order(s) settled", changed)
    return changed
