"""
CORS/CSRF configuration component (Django Implementation Blueprint §12).

CSRF is disabled for the JWT-authenticated API surface (stateless token
auth) but remains enforced for the session-cookie-authenticated Django
Admin. CORS uses an explicit origin allowlist -- never
`CORS_ALLOW_ALL_ORIGINS = True` in any environment, including
development, per the same document.
"""
from __future__ import annotations

import os


def _split_env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


CORS_ALLOWED_ORIGINS = _split_env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False  # never overridden, in any environment

CSRF_TRUSTED_ORIGINS = _split_env_list("CSRF_TRUSTED_ORIGINS")
CSRF_COOKIE_SECURE = os.environ.get("DJANGO_ENV", "development") == "production"
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = os.environ.get("DJANGO_ENV", "development") == "production"
