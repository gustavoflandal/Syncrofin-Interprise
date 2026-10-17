"""Logging estruturado em JSON para produção e texto legível para desenvolvimento.

Configuração única chamada em startup — não usa basicConfig porque o Uvicorn
já registra seus próprios handlers; em vez disso, reconfigura o root logger
para emitir JSON quando LOG_FORMAT=json (padrão em produção).

Campos emitidos em cada linha:
  timestamp  — ISO-8601 UTC
  level      — DEBUG / INFO / WARNING / ERROR / CRITICAL
  logger     — nome do logger Python
  message    — mensagem
  request_id — propagado do contexto da requisição quando disponível
  trace_id / span_id — do span OpenTelemetry ativo (só com tracing ligado)
  + quaisquer extras passados para o logger
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings


def _trace_ids() -> tuple[str, str] | None:
    """trace_id/span_id (hex) do span ativo, ou None sem OTel/sem span válido."""
    try:
        from opentelemetry import trace

        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
    except Exception:  # OTel ausente ou não inicializado: log segue sem os campos
        pass
    return None


class _JsonFormatter(logging.Formatter):
    """Emite uma linha JSON por registro."""

    def format(self, record: logging.LogRecord) -> str:
        doc: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # request_id injetado pelo RequestContextMiddleware via LogRecord.extra
        if rid := getattr(record, "request_id", None):
            doc["request_id"] = rid

        if ids := _trace_ids():
            doc["trace_id"], doc["span_id"] = ids

        # quaisquer campos extras passados como kwargs para o logger
        _STDLIB_ATTRS = frozenset(logging.LogRecord.__dict__) | {
            "message", "asctime", "exc_info", "exc_text", "stack_info",
        }
        for key, val in record.__dict__.items():
            if key not in _STDLIB_ATTRS and not key.startswith("_"):
                doc[key] = val

        if record.exc_info:
            doc["exception"] = "".join(traceback.format_exception(*record.exc_info)).strip()

        return json.dumps(doc, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Chame uma vez no startup do processo (antes de qualquer log)."""
    settings = get_settings()
    use_json = getattr(settings, "log_format", "text").lower() == "json"

    fmt: logging.Formatter
    if use_json:
        fmt = _JsonFormatter()
    else:
        fmt = logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    level_name = getattr(settings, "log_level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    # Remove handlers adicionados pelo Uvicorn/Gunicorn para evitar duplicatas
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    root.addHandler(handler)
    root.setLevel(level)

    # Silencia loggers muito verbosos por padrão
    for noisy in ("sqlalchemy.engine", "httpx", "httpcore", "celery.beat"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
