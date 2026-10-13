"""
Production settings.

Security headers hardened per Django Implementation Blueprint §12;
DEBUG is unconditionally False and cannot be overridden by environment
variable, since a misconfigured DEBUG=True in production is one of the
most damaging possible deployment mistakes.
"""
import os

from config.settings.base import *  # noqa: F401,F403

DEBUG = False

if not ALLOWED_HOSTS:  # noqa: F405
    raise RuntimeError("ALLOWED_HOSTS must be set in production.")

# A missing or weak key signs every session, JWT and password-reset token -- refuse to start rather than run with one.
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure"):  # noqa: F405
    raise RuntimeError("SECRET_KEY must be set in production to a random value of at least 50 characters.")

# The API map (schema / Swagger / ReDoc) stays private in production unless deliberately opened.
API_DOCS_ENABLED = os.environ.get("API_DOCS_ENABLED", "false").lower() == "true"

# HTTPS-dependent security settings are explicit opt-in, not
# unconditionally True. Rationale: the currently-mounted
# docker/nginx/nginx.conf is HTTP-only by design (the HTTPS template,
# docker/nginx/nginx.https.conf.template, documents its own 6-step
# activation procedure and is deliberately inactive until a real
# production domain exists to obtain a real TLS certificate against).
# If SECURE_SSL_REDIRECT/SECURE_HSTS_* were unconditionally True here,
# deploying with DJANGO_ENV=production today -- before that nginx
# switch-over happens -- would make Django redirect every request to
# https:// and send Strict-Transport-Security (including the
# effectively-irreversible preload directive) against a server that
# doesn't listen on port 443 at all, exactly what the HTTPS template's
# own step 6 explicitly warns against enabling prematurely.
#
# Set NUTRIZONE_HTTPS_READY=true only once the HTTPS nginx config is
# actually active and confirmed working end-to-end.
_HTTPS_READY = os.environ.get("NUTRIZONE_HTTPS_READY", "false").lower() == "true"

SECURE_SSL_REDIRECT = _HTTPS_READY
SESSION_COOKIE_SECURE = _HTTPS_READY
CSRF_COOKIE_SECURE = _HTTPS_READY
SECURE_HSTS_SECONDS = 31536000 if _HTTPS_READY else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = _HTTPS_READY
SECURE_HSTS_PRELOAD = _HTTPS_READY
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

NUTRIZONE_STORAGE_BACKEND = os.environ.get("NUTRIZONE_STORAGE_BACKEND", "local")

# JSON_LOGS is read by config/settings/components/logging.py at import
# time (before this file runs), so structured JSON logging in
# production is controlled by setting the JSON_LOGS=true environment
# variable at deploy time, not by an override here.

# --- Error monitoring (Sentry) ---------------------------------------------------------------------------------
# sentry-sdk ships in requirements/production.txt; it reports only when SENTRY_DSN is set. No personal data is sent
# (send_default_pii=False); performance tracing is sampled by SENTRY_TRACES_SAMPLE_RATE (default 0 = errors only).
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        environment=os.environ.get("SENTRY_ENVIRONMENT", "production"),
        release=os.environ.get("APP_RELEASE") or None,
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
        send_default_pii=False,
    )
