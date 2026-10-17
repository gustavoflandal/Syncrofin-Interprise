"""Testes dos endpoints de observabilidade (E5).

  GET /api/ready   — verifica DB + Redis, retorna 200 ou 503
  GET /api/metrics — formato de texto Prometheus
"""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ready_ok(client: AsyncClient):
    response = await client.get("/api/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["db"] == "ok"
    assert body["checks"]["redis"] == "ok"


@pytest.mark.asyncio
async def test_ready_db_down(client: AsyncClient):
    from sqlalchemy.exc import OperationalError

    with patch(
        "app.core.database.async_session_maker",
        side_effect=OperationalError("conn", None, None),
    ):
        response = await client.get("/api/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["status"] == "unavailable"
    assert "db" in body["detail"]["failed"]


@pytest.mark.asyncio
async def test_ready_redis_down(client: AsyncClient):
    mock_redis = AsyncMock()
    mock_redis.ping.side_effect = ConnectionError("redis down")

    with patch("app.core.redis.get_redis", return_value=mock_redis):
        response = await client.get("/api/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["detail"]["status"] == "unavailable"
    assert "redis" in body["detail"]["failed"]


@pytest.mark.asyncio
async def test_metrics_content_type(client: AsyncClient):
    response = await client.get("/api/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_metrics_contains_expected_metric(client: AsyncClient):
    # Dispara uma requisição qualquer para que o contador seja incrementado
    await client.get("/api/health")

    response = await client.get("/api/metrics")
    assert response.status_code == 200
    # O contador http_requests_total deve estar presente
    assert b"http_requests_total" in response.content


@pytest.mark.asyncio
async def test_metrics_contains_histogram(client: AsyncClient):
    response = await client.get("/api/metrics")
    assert response.status_code == 200
    assert b"http_request_duration_seconds" in response.content
