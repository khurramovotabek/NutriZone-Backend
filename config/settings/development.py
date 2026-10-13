"""Development settings. Imports base, overrides only what differs."""
from config.settings.base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Looser throttle rates locally so manual testing isn't rate-limited.
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"anon": "1000/min", "user": "1000/min"}}  # noqa: F405

CORS_ALLOWED_ORIGINS = CORS_ALLOWED_ORIGINS or ["http://localhost:3000"]  # noqa: F405

# Emit real emails/SMS to console instead of a provider in development.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
