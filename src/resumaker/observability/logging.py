"""Structured logging. One line of JSON per event to stdout - grep-able locally and
ingestible by any log collector on a VM (Grafana/Loki, CloudWatch, etc.) with zero
extra infra.

Rules:
  - `configure_logging()` once at process start (API/CLI entrypoints call it).
  - Never log PII (contact details, full resume text). Log ids, counts, timings.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

_CONFIGURED = False


class JsonFormatter(logging.Formatter):
    """Render a log record as a single JSON object. Extra fields passed via
    `logger.info(msg, extra={"extra": {...}})` are merged in."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra", None)
        if isinstance(extra, dict):
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    _CONFIGURED = True


def get_logger(name: str) -> logging.LoggerAdapter:
    """Return a logger whose `extra=` kwargs land in the JSON payload under `extra`."""
    return _ExtraAdapter(logging.getLogger(name), {})


class _ExtraAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.pop("extra", None)
        if extra:
            kwargs["extra"] = {"extra": extra}
        return msg, kwargs
