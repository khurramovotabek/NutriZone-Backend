"""
Testing settings.

Real PostgreSQL (never SQLite -- Django Implementation Blueprint §11:
the codebase depends on Postgres-specific features: JSONB, PostGIS,
native enums, partial indexes). Celery runs eager/synchronous so tests
don't need a live broker; Channels layer switches to the in-memory
backend for the same reason.
"""
from config.settings.base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = SECRET_KEY or "test-secret-key-not-for-production"  # noqa: F405

# Django's own test client (and DRF's APIClient, which wraps it) issues
# requests with HTTP_HOST="testserver" by default -- without this, every
# test that exercises a real view via the test client fails at the
# ALLOWED_HOSTS check before ever reaching application code, regardless
# of what ALLOWED_HOSTS is set to via the environment for real requests.
ALLOWED_HOSTS = [*ALLOWED_HOSTS, "testserver"]  # noqa: F405

DATABASES["default"]["NAME"] = f"test_{DATABASES['default']['NAME']}"  # noqa: F405

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast hashing for test speed only

REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}  # noqa: F405

MEDIA_ROOT = "/tmp/nutrizone-test-media"  # noqa: F405

# Real, closed gap: base.py reads PUBLIC_BASE_URL straight from the
# environment, so any developer whose .env.local happens to have it
# set (e.g. to a temporary Cloudflare tunnel domain, for local
# Telegram-webhook testing) got tests asserting the *relative*-URL
# default (e.g. reviews' test_public_media_list_returns_a_full_usable_url)
# failing purely from ambient env leakage, never from a real defect --
# pinned here, same as MEDIA_ROOT/NUTRIZONE_SMS_LOGIN_ENABLED above,
# so the test suite's behavior is deterministic regardless of the
# developer's local .env.local.
PUBLIC_BASE_URL = None
GEOCODER_ENABLED = False  # never call OpenStreetMap from tests; tests patch geocoder._get

# Real, closed gap, same root cause and same fix as PUBLIC_BASE_URL just
# above: base.py reads TELEGRAM_BOT_TOKEN straight from the environment,
# so a developer whose .env.local has the project's real bot token
# configured got tests that only ever pass a fake test token via the
# `settings` fixture (e.g. "123456:TEST-TOKEN") silently talking to the
# *real* Telegram Bot API instead of getting the
# TelegramGatewayConfigurationError/mocked response they were written to
# expect -- pinned empty here so the test suite is deterministic
# regardless of the developer's local .env.local.
TELEGRAM_BOT_TOKEN = ""

# Same root cause and same fix as TELEGRAM_BOT_TOKEN just above, for the
# separate Orders Bot token (see base.py's own comment on it).
TELEGRAM_ORDERS_BOT_TOKEN = ""

# Same root cause and same fix again: base.py reads TELEGRAM_ORDERS_CHAT_ID
# straight from the environment, so a developer whose .env.local has the
# real Orders Channel activated got telegram_bot.checks's own Orders Bot
# warnings (W004/W005) firing on tests that never configured the Orders
# Bot at all, purely from ambient env leakage -- pinned empty here so the
# test suite is deterministic regardless of the developer's local .env.local.
TELEGRAM_ORDERS_CHAT_ID = ""
# NutriZoneAnalyticsBot: same reason -- tests must never pick up the developer's real bot/recipients from .env.
TELEGRAM_ANALYTICS_BOT_TOKEN = ""
ANTHROPIC_API_KEY = ""  # tests never call the real API (the engine takes an injected client)
TELEGRAM_ANALYTICS_CHAT_IDS = ""
TELEGRAM_ANALYTICS_WEBHOOK_SECRET = ""

# Real regression found and fixed, same root cause and same fix as
# PUBLIC_BASE_URL/TELEGRAM_BOT_TOKEN above: base.py reads
# OTP_MAX_REQUESTS_PER_HOUR straight from the environment, so a
# developer whose .env.local raises it for local manual testing (see
# that file's own comment) got
# TestOTPMaxAttemptsNeverCrashesTheWebhook's hourly-quota test silently
# failing purely from ambient env leakage -- pinned to the real
# production default here so the test suite is deterministic
# regardless of the developer's local .env.local.
OTP_MAX_REQUESTS_PER_HOUR = 3

# Real regression found and fixed: many existing tests across
# unrelated modules (Wishlist, Reviews, etc.) use /auth/request-otp
# purely as a generic "create a real authenticated customer" fixture
# helper, unrelated to the SMS-specific product decision to disable it
# by default (see base.py's own NUTRIZONE_SMS_LOGIN_ENABLED). Enabled
# here, in the test environment only, so that existing test
# infrastructure keeps working without each test file needing its own
# settings override.
NUTRIZONE_SMS_LOGIN_ENABLED = True

# The suite asserts Django/admin chrome in English; production serves the dashboard in Uzbek (base.LANGUAGE_CODE).
LANGUAGE_CODE = "en"
