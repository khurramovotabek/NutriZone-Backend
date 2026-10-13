"""
Structured logging configuration (Django Implementation Blueprint §6/§12).

Separate named loggers for application, API, security, background
tasks, errors, and audit -- each independently routable (to files in
development, to centralized log shipping in production, both configured
via the same handler definitions so environments differ only in handler
targets, not in logger structure).
"""
from __future__ import annotations

import os

LOG_LEVEL = os.environ.get("DJANGO_LOG_LEVEL", "INFO")
LOG_DIR = os.environ.get("LOG_DIR", "logs")
JSON_LOGS = os.environ.get("JSON_LOGS", "false").lower() == "true"

_formatter = "json" if JSON_LOGS else "human"


def _file_handler(filename: str) -> dict:
    return {
        "class": "logging.handlers.RotatingFileHandler",
        "filename": os.path.join(LOG_DIR, filename),
        "maxBytes": 50 * 1024 * 1024,
        "backupCount": 10,
        "formatter": _formatter,
        "filters": ["context"],
    }


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "context": {"()": "common.utils.logging_filters.ContextFilter"},
    },
    "formatters": {
        "human": {
            "format": "%(asctime)s [%(levelname)s] %(name)s (req=%(request_id)s actor=%(actor_id)s): %(message)s",
        },
        "json": {"()": "common.utils.logging_filters.JSONFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": _formatter,
            "filters": ["context"],
        },
        "application_file": _file_handler("application.log"),
        "api_file": _file_handler("api.log"),
        "security_file": _file_handler("security.log"),
        "tasks_file": _file_handler("background_tasks.log"),
        "errors_file": _file_handler("errors.log"),
        "audit_file": _file_handler("audit.log"),
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "nutrizone.app": {
            "handlers": ["console", "application_file"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "nutrizone.api": {
            "handlers": ["console", "api_file"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "nutrizone.security": {
            "handlers": ["console", "security_file"],
            "level": "INFO",
            "propagate": False,
        },
        "nutrizone.tasks": {
            "handlers": ["console", "tasks_file"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "nutrizone.errors": {
            "handlers": ["console", "errors_file"],
            "level": "WARNING",
            "propagate": False,
        },
        "nutrizone.audit": {
            "handlers": ["console", "audit_file"],
            "level": "INFO",
            "propagate": False,
        },
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "errors_file"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
