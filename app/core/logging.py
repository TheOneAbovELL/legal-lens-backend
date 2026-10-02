"""Structured (JSON) logging with request context and secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from contextvars import ContextVar
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"gsk_[A-Za-z0-9]{8,}"),  # Groq keys
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),  # OpenAI/Anthropic-style keys
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-_\.=]{10,}"),
    re.compile(r"(?i)((?:api[_-]?key|password|secret|token)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]{4,}"),
)

_RESERVED = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        request_id = request_id_var.get()
        extras = {
            k: v for k, v in record.__dict__.items() if k not in _RESERVED and not k.startswith("_")
        }
        suffix = f" {extras}" if extras else ""
        prefix = f"[{request_id}] " if request_id else ""
        return redact(prefix + base + suffix)


def configure_logging(level: str = "INFO", json_logs: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter() if json_logs else TextFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Third-party libraries are noisy at INFO and may log request URLs.
    for noisy in ("httpx", "httpcore", "urllib3", "neo4j", "sentence_transformers", "transformers"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, logging.getLevelName(level)))
    logging.getLogger("uvicorn.access").disabled = True  # replaced by our access log


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
