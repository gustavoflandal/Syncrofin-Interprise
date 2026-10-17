"""Métricas Prometheus e middleware de logging estruturado por requisição.

Expõe:
  http_requests_total{method, path, status}  — contador
  http_request_duration_seconds{method, path} — histograma de latência

O path é normalizado (UUIDs e inteiros substituídos por ``{id}``) para não
explodir a cardinalidade das séries temporais.

Uso:
  GET /api/metrics  — retorna o formato de texto do Prometheus (scrape)
"""
from __future__ import annotations

import logging
import re
import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registro isolado — não usa o REGISTRY global para não misturar com métricas
# internas do processo (gc, threads, etc.) que poluiriam o endpoint.
# ---------------------------------------------------------------------------
_REGISTRY = CollectorRegistry(auto_describe=True)

_REQUESTS = Counter(
    "http_requests_total",
    "Total de requisições HTTP",
    ["method", "path", "status"],
    registry=_REGISTRY,
)

_DURATION = Histogram(
    "http_request_duration_seconds",
    "Latência das requisições HTTP",
    ["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=_REGISTRY,
)

# Padrões de path que não vale instrumentar individualmente
_SKIP_PATHS = frozenset({"/api/metrics", "/api/health", "/api/ready"})

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_INT_RE = re.compile(r"/\d+(/|$)")


def _normalize(path: str) -> str:
    """Substitui IDs dinâmicos por ``{id}`` para limitar cardinalidade."""
    path = _UUID_RE.sub("{id}", path)
    path = _INT_RE.sub(r"/{id}\1", path)
    return path


def metrics_response() -> Response:
    """Gera a resposta de scrape para o Prometheus."""
    data = generate_latest(_REGISTRY)
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)


class MetricsMiddleware:
    """Registra latência, contadores e loga cada requisição como JSON.

    Deve ser adicionado DEPOIS do RequestContextMiddleware para que o
    request_id já esteja no contexto.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path
        method = request.method

        if path in _SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        norm_path = _normalize(path)
        start = time.perf_counter()
        status_code = 500

        async def _send_with_capture(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send_with_capture)
        finally:
            duration = time.perf_counter() - start
            _REQUESTS.labels(method=method, path=norm_path, status=str(status_code)).inc()
            _DURATION.labels(method=method, path=norm_path).observe(duration)

            # request_id já está no X-Request-ID, mas não no LogRecord ainda —
            # passamos como extra para que o JsonFormatter o inclua.
            from app.core.audit_context import audit_context  # local import
            ctx = audit_context.get(None)
            rid = ctx.request_id if ctx else None

            extra = {"request_id": rid, "http_method": method, "http_path": path,
                     "http_status": status_code, "duration_ms": round(duration * 1000, 1)}

            if status_code >= 500:
                logger.error("request completed", extra=extra)
            elif status_code >= 400:
                logger.warning("request completed", extra=extra)
            else:
                logger.info("request completed", extra=extra)
