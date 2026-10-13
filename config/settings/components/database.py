"""
Database configuration component.

One PostgreSQL 16 cluster, schema-per-bounded-context (Enterprise
Database Blueprint §1.1). At foundation stage this configures the
single `default` connection; per-app schema routing (via `db_table`
qualified names or a custom database router) is added when the first
business module's models are written -- deferred deliberately, since
this document's scope is infrastructure only.
"""
from __future__ import annotations

import os

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "nutrizone"),
        "USER": os.environ.get("POSTGRES_USER", "nutrizone"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": int(os.environ.get("POSTGRES_CONN_MAX_AGE", "60")),
        "OPTIONS": {
            "connect_timeout": 5,
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
