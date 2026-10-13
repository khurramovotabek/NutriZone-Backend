"""
Logging filters/formatters supporting structured (JSON-in-production)
logging (Django Implementation Blueprint §6/§12).

Injects `request_id` and `actor_id` into every log record so log lines
can be correlated to a single request/task, per the "request/task
correlation ID" requirement.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from common.middleware.audit_context import get_current_actor_id, get_current_request_id


class ContextFilter(logging.Filter):
    """Attaches request_id/actor_id to every LogRecord that passes through it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_current_request_id() or "-"
        actor_id = get_current_actor_id()
        record.actor_id = str(actor_id) if actor_id else "-"
        return True


class JSONFormatter(logging.Formatter):
    """Production log formatter -- one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "actor_id": getattr(record, "actor_id", "-"),
            "module": record.module,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)
