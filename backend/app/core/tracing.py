"""Tracing distribuído com OpenTelemetry (E5).

Totalmente opcional: sem ``OTEL_EXPORTER_OTLP_ENDPOINT`` nada é importado nem
instrumentado (o custo em produção sem coletor é zero). Com o endpoint definido,
instrumenta as rotas FastAPI e as queries SQLAlchemy e exporta os spans via OTLP
(gRPC por padrão; ``OTEL_EXPORTER_OTLP_PROTOCOL=http`` usa OTLP/HTTP).

Os imports do OTel ficam dentro das funções de propósito: o módulo continua
importável (e o app sobe) mesmo se o pacote faltar numa imagem customizada.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Idempotência: o provider global do OTel só aceita um set_tracer_provider.
_initialized = False


def _build_exporter(endpoint: str, protocol: str) -> Any:
    if protocol.lower().startswith("http"):
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    else:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    return OTLPSpanExporter(endpoint=endpoint)


def setup_tracing(app: FastAPI, settings: Settings | None = None) -> bool:
    """Liga o tracing se houver endpoint configurado. Devolve True se está ativo."""
    global _initialized
    settings = settings or get_settings()
    endpoint = (settings.otel_exporter_endpoint or "").strip()
    if not endpoint:
        return False
    if _initialized:
        return True

    try:
        from opentelemetry import trace
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        from app.core.database import engine

        provider = TracerProvider(
            resource=Resource.create({"service.name": settings.otel_service_name})
        )
        provider.add_span_processor(
            BatchSpanProcessor(_build_exporter(endpoint, settings.otel_exporter_protocol))
        )
        trace.set_tracer_provider(provider)

        # /api/health, /api/ready e /api/metrics geram ruído (probes a cada poucos s).
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=provider,
            excluded_urls="/api/health,/api/ready,/api/metrics",
        )
        # Engine assíncrono: o instrumentador precisa do engine síncrono interno.
        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine, tracer_provider=provider
        )
    except Exception:
        # Observabilidade nunca derruba a aplicação.
        logger.exception("tracing: falha ao inicializar OpenTelemetry; seguindo sem tracing")
        return False

    _initialized = True
    logger.info(
        "tracing: OpenTelemetry ativo",
        extra={"otel_endpoint": endpoint, "otel_service": settings.otel_service_name},
    )
    return True
