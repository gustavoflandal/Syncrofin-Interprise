"""Tracing OpenTelemetry (E5): no-op sem endpoint, ativação com endpoint, trace_id nos logs."""
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from app.core import tracing
from app.core.logging_config import _JsonFormatter


def _settings(endpoint: str):
    return SimpleNamespace(
        otel_exporter_endpoint=endpoint,
        otel_service_name="syncrofin-backend",
        otel_exporter_protocol="grpc",
    )


@pytest.fixture(autouse=True)
def _reset_tracing(monkeypatch):
    monkeypatch.setattr(tracing, "_initialized", False)


def _record(msg="olá"):
    return logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None)


def test_setup_tracing_is_noop_without_endpoint():
    app = FastAPI()
    assert tracing.setup_tracing(app, _settings("")) is False
    assert tracing._initialized is False
    assert not getattr(app, "_is_instrumented_by_opentelemetry", False)


def test_setup_tracing_initializes_with_endpoint(monkeypatch):
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    exporter = InMemorySpanExporter()
    seen = {}

    def fake_build(endpoint, protocol):
        seen["args"] = (endpoint, protocol)
        return exporter

    monkeypatch.setattr(tracing, "_build_exporter", fake_build)
    app = FastAPI()
    try:
        assert tracing.setup_tracing(app, _settings("http://collector:4317")) is True
        assert seen["args"] == ("http://collector:4317", "grpc")
        assert app._is_instrumented_by_opentelemetry is True
        # Idempotente: a segunda chamada não reconstrói o exporter.
        seen.clear()
        assert tracing.setup_tracing(app, _settings("http://collector:4317")) is True
        assert seen == {}
    finally:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.uninstrument_app(app)
        SQLAlchemyInstrumentor().uninstrument()


def test_json_log_has_no_trace_fields_without_active_span():
    doc = json.loads(_JsonFormatter().format(_record()))
    assert "trace_id" not in doc and "span_id" not in doc


def test_json_log_includes_trace_id_with_active_span():
    from opentelemetry.sdk.trace import TracerProvider

    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("op") as span:
        ctx = span.get_span_context()
        doc = json.loads(_JsonFormatter().format(_record()))
    assert doc["trace_id"] == format(ctx.trace_id, "032x")
    assert doc["span_id"] == format(ctx.span_id, "016x")
