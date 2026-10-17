"""Endpoints de saúde e métricas (E5).

  GET /api/health  — resposta estática rápida (liveness: o processo está vivo)
  GET /api/ready   — verifica DB + Redis (readiness: pode receber tráfego)
  GET /api/metrics — formato de texto Prometheus (scrape de métricas)

/api/health continua onde estava (em main.py); /api/ready e /api/metrics
ficam aqui para não poluir o main.
"""
import logging

from fastapi import APIRouter, HTTPException, status

from app.core.metrics import metrics_response

router = APIRouter(tags=["observability"])
logger = logging.getLogger(__name__)


@router.get("/api/ready", include_in_schema=False)
async def readiness():
    """Verifica DB e Redis antes de declarar o serviço pronto.

    Retorna 200 quando ambos respondem, 503 caso contrário.
    Kubernetes/balanceadores usam este endpoint no ``readinessProbe``.
    """
    errors: list[str] = []

    # --- Postgres ----------------------------------------------------------
    try:
        from sqlalchemy import text
        from app.core.database import async_session_maker
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("readiness: db check failed", extra={"error": str(exc)})
        errors.append("db")

    # --- Redis -------------------------------------------------------------
    try:
        from app.core.redis import get_redis
        r = await get_redis()
        await r.ping()
    except Exception as exc:
        logger.error("readiness: redis check failed", extra={"error": str(exc)})
        errors.append("redis")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unavailable", "failed": errors},
        )

    return {"status": "ready", "checks": {"db": "ok", "redis": "ok"}}


@router.get("/api/metrics", include_in_schema=False)
async def prometheus_metrics():
    """Endpoint de scrape no formato de texto do Prometheus.

    Protegido apenas por rede (sem auth) — expor somente na rede interna
    ou atrás de um proxy que restrinja o acesso.
    """
    return metrics_response()
