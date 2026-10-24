"""
Base Django settings, common to every environment.

`development.py` / `testing.py` / `production.py` each import * from
here and override only what genuinely differs (Django Implementation
Blueprint §7) -- no setting is defined independently in more than one
environment file.
"""
from __future__ import annotations

import os
from pathlib import Path

from config.settings.components.celery import *  # noqa: F401,F403
from config.settings.components.channels import *  # noqa: F401,F403
from config.settings.components.cors import *  # noqa: F401,F403
from config.settings.components.database import *  # noqa: F401,F403
from config.settings.components.jazzmin import *  # noqa: F401,F403
from config.settings.components.jwt import *  # noqa: F401,F403
from config.settings.components.logging import *  # noqa: F401,F403
from config.settings.components.payment_webhook import *  # noqa: F401,F403
from config.settings.components.storage import *  # noqa: F401,F403

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Core / security
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "")

# OpenAPI schema + Swagger/ReDoc. On in development; production keeps the API map private unless explicitly
# opened with API_DOCS_ENABLED=true (config/settings/production.py).
API_DOCS_ENABLED = os.environ.get("API_DOCS_ENABLED", "true").lower() == "true"
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY must be set via environment variable. "
        "See Django Implementation Blueprint §7 -- the application refuses "
        "to start with an insecure default."
    )

DEBUG = False
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]

# Real, product-required override point: `apps.identity.domain.services.
# OTPPolicy.assert_within_hourly_quota`'s own real production quota (3
# requests/hour/phone number) stays the hard-coded, unchangeable
# domain default -- this setting only ever raises it, and only when an
# operator explicitly does so via the environment (e.g. `.env.local`
# during development, where repeatedly testing the OTP flow otherwise
# hits the same real quota a customer would). Left unset, production
# gets the exact same, unmodified 3/hour security control as before.
OTP_MAX_REQUESTS_PER_HOUR = int(os.environ.get("OTP_MAX_REQUESTS_PER_HOUR", "3"))

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    # One server for HTTP *and* WebSockets: with daphne first, `manage.py
    # runserver` serves config.asgi (Channels) instead of plain WSGI, so
    # starting the backend starts realtime chat too -- no separate
    # WebSocket process to run. Must precede django.contrib.staticfiles
    # (daphne's own runserver override).
    "daphne",
    "jazzmin",  # must precede django.contrib.admin -- Jazzmin's own documented requirement
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    "channels",
    "django_celery_beat",
    "django_celery_results",
]

# `core` is platform infrastructure (not a bounded context) but is
# registered so its AppConfig.ready() hook can wire process-wide
# singletons (FeatureFlags provider chain) once Django's app registry
# is available -- see core/apps.py.
PLATFORM_INFRA_APPS = [
    "core.apps.CoreConfig",
]

# Every bounded-context app, per Django Implementation Blueprint §2's App
# Catalogue -- no business models exist yet, but each app is a registered
# Django application from day one so the dependency-direction CI check
# (import-linter) has a stable app registry to validate against.
LOCAL_APPS = [
    "apps.identity",
    # NOTE: "apps.catalog" below is the empty placeholder scaffolded in
    # the Foundation phase, matching the Domain Architecture
    # Specification's bounded-context name "Catalog". The actual
    # Products & Catalog implementation was built under "apps.products"
    # (per this module's explicit implementation instructions), not
    # "apps.catalog" -- both are registered here so neither placeholder
    # scaffold nor the real implementation is silently dropped, but
    # this naming duplication should be reconciled (most likely by
    # removing the unused "apps/catalog/" placeholder folder) before
    # this is considered final. Flagged explicitly rather than resolved
    # unilaterally, per this project's own amendment-discipline rule.
    "apps.catalog",
    "apps.products",
    "apps.geo",
    "apps.pricing",
    "apps.inventory",
    # NOTE: "apps.cart" was entirely absent from the original Foundation
    # scaffold (no folder, no INSTALLED_APPS entry) -- unlike every
    # other bounded context, which had at least placeholder scaffolding
    # provisioned in advance. Added here at the start of Cart's own
    # Phase 1 as the minimum-necessary fix so a later Infrastructure
    # phase (which requires a real AppConfig for ORM models) doesn't
    # hit this gap mid-build.
    "apps.cart",
    "apps.ordering",
    "apps.payment",
    "apps.coupons",
    "apps.loyalty",
    "apps.reviews",
    "apps.stores",
    "apps.chat",
    "apps.notifications",
    "apps.telegram_bot",
    "apps.pos",
    "apps.search",
    "apps.content",
    "apps.platform",
    "apps.audit",
    "apps.assistant",
    "apps.support",
    "apps.receipts",
    "apps.finance",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + PLATFORM_INFRA_APPS + LOCAL_APPS

# Every bounded context's migrations live under its own
# `infrastructure/migrations/` package (Clean Architecture: migrations
# are an Infrastructure-layer concern), not Django's own default
# `<app_package>/migrations/`. Without this mapping, `makemigrations`
# silently writes to the wrong, Django-default location instead of the
# project's own established convention -- confirmed as a genuine,
# repository-wide gap by actually running `makemigrations` (Django
# Implementation Blueprint compatibility audit), not assumed. Derived
# dynamically from `LOCAL_APPS`'s own dotted paths rather than
# hardcoded, so it can never silently drift out of sync with the
# actual list of local apps.
MIGRATION_MODULES = {
    app_path.rsplit(".", 1)[-1]: f"{app_path}.infrastructure.migrations" for app_path in LOCAL_APPS
}

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
# RequestIDMiddleware / AuditContextMiddleware are placed after
# AuthenticationMiddleware so request.user is already resolved (Django
# Implementation Blueprint §5) and before CommonMiddleware/others that
# might log.
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "apps.platform.infrastructure.admin_i18n.AdminTextTranslationMiddleware",  # dashboard HTML phrase by phrase in the staff language (locale/*/admin_phrases.po)
    "apps.platform.infrastructure.branding.AdminBrandingMiddleware",  # Jazzmin header/footer/login follow SiteSettings.site_name  # Phase 08.1: activates the already-configured LANGUAGES/LOCALE_PATHS for the admin dashboard's own language switcher
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "common.middleware.request_id.RequestIDMiddleware",
    "core.observability.middleware.CorrelationMiddleware",
    "common.middleware.audit_context.AuditContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(BASE_DIR / "templates")],  # Phase 08.1: must take priority over jazzmin's own app-level templates (jazzmin precedes apps.platform in INSTALLED_APPS)
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.platform.infrastructure.context_processors.site_branding",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Password validation (Django Admin superuser/staff accounts only --
# customer auth is OTP/Google/Telegram per REST API Blueprint §4, not
# password-based)
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization (Architecture Review: uz/ru/en, architecture-level
# localization, not hardcoded)
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("uz", "O'zbekcha"),
    ("ru", "Русский"),
    ("en", "English"),
]
LOCALE_PATHS = [str(BASE_DIR / "locale")]

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "common.pagination.StandardPageNumberPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "common.exceptions.handlers.nutrizone_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # Coarse global tiers (REST API Blueprint §18); endpoint-specific
        # business-aware limits are enforced in application/ via
        # core/idempotency & a rate-limit decorator once business
        # modules exist.
        "anon": "100/min",
        "user": "300/min",
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# ---------------------------------------------------------------------------
# drf-spectacular (OpenAPI / Swagger / ReDoc) -- REST API Blueprint §17
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "NutriZone API",
    "DESCRIPTION": "Premium Sport Nutrition & Vitamins Platform -- Enterprise REST API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]+",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "SWAGGER_UI_SETTINGS": {"deepLinking": True, "persistAuthorization": True},
    "POSTPROCESSING_HOOKS": ["core.openapi.hooks.add_standard_headers"],
    "TAGS": [
        {"name": "Identity", "description": "Authentication, profile, and session management (self-service)."},
        {"name": "Identity Admin", "description": "Staff-only user administration and RBAC endpoints."},
        {"name": "Products", "description": "Public product catalog browsing and search."},
        {"name": "Products Admin", "description": "Staff-only product/catalog administration."},
        {"name": "Geo", "description": "Public administrative-hierarchy lookups, search, and geocoding."},
        {"name": "Geo Admin", "description": "Staff-only Country/Region/District/City/Neighborhood/Boundary administration."},
        {"name": "Geo Addresses", "description": "Self-service address management."},
        {"name": "Store", "description": "Public store lookups and search."},
        {"name": "Store Admin", "description": "Staff-only store/branch/warehouse/coverage administration."},
        {"name": "Inventory", "description": "Public/internal stock level lookups."},
        {"name": "Inventory Admin", "description": "Staff-only stock operations, batch/serial tracking, counts, and snapshots."},
        {"name": "Pricing", "description": "Public/internal price lookups and calculation."},
        {"name": "Pricing Admin", "description": "Staff-only price list, pricing rule, campaign, coupon, and bundle price administration."},
        {"name": "Cart", "description": "Guest/authenticated shopping cart operations."},
        {"name": "Cart Admin", "description": "Staff-only cart search, listing, and support tooling."},
        {"name": "Ordering", "description": "Order checkout, lifecycle, returns, and cancellations."},
        {"name": "Ordering Admin", "description": "Staff-only order search, listing, and support tooling."},
        {"name": "Return Operations", "description": "Order return request, approval, receipt, and refund workflow."},
        {"name": "Cancellation Operations", "description": "Formal order cancellation request and approval workflow."},
        {"name": "Invoice Operations", "description": "Order invoice issuance and retrieval."},
        {"name": "Reviews", "description": "Customer product reviews, ratings, and media."},
        {"name": "Reviews Admin", "description": "Staff-only review moderation and statistics."},
        {"name": "Chat", "description": "Customer/staff conversations and messages."},
        {"name": "Chat Admin", "description": "Staff-only conversation lifecycle management and statistics."},
        {"name": "Notifications", "description": "User-scoped notifications and preferences."},
        {"name": "Notifications Admin", "description": "System/admin-initiated notification creation."},
        {"name": "POS", "description": "Point-of-sale transactions (Sale lifecycle)."},
        # One tag per additional bounded-context module, matching REST
        # API Blueprint §13's numbering -- populated as each module
        # ships its own endpoints.
    ],
}

# ---------------------------------------------------------------------------
# Redis (general cache; Celery/Channels have their own URLs above)
# ---------------------------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# Real, closed gap: this was never configured at all outside
# config/settings/testing.py's own InMemoryChannelLayer (which only
# works inside a single process). The `channels` ASGI worker (real-time
# WebSocket connections) and the `web`/Celery WSGI/worker processes
# (where a message is actually sent and, per apps/chat/interfaces/api/v1/views.py,
# now calls channel_layer.group_send) are separate processes -- an
# in-memory layer can never deliver between them. `channels-redis` was
# already a real dependency (requirements/base.txt), just unwired.
# Reuses the same Redis instance/URL every other module's ephemeral
# state already uses -- no second Redis deployment.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL]},
    }
}

# ---------------------------------------------------------------------------
# Feature flags (infrastructure toggle only -- business feature flags
# live in the `platform` app's feature_flags table, Django
# Implementation Blueprint §7)
# ---------------------------------------------------------------------------
NUTRIZONE_INFRA_FLAGS = {
    "ENABLE_CHANNELS": os.environ.get("ENABLE_CHANNELS", "true").lower() == "true",
}

# --- Identity module ---------------------------------------------------
# Config-driven OTP provider swap point (Django Implementation Blueprint
# §7) -- see apps/identity/infrastructure/gateways/otp_providers.py.
# "console" (logs the code, sends nothing real) is the only provider
# with a working implementation; the SMS vendor decision itself is
# still open per Architecture Review §11.
NUTRIZONE_OTP_PROVIDER = os.environ.get("NUTRIZONE_OTP_PROVIDER", "console")

# Eskiz.uz SMS gateway credentials (Phase 04) -- never hardcoded, absent
# by default so local/test environments never accidentally attempt a real
# call. EskizOTPProvider itself fails loudly (ConfigurationError) if
# selected via NUTRIZONE_OTP_PROVIDER without these being set, rather
# than silently falling back to a different provider.
ESKIZ_EMAIL = os.environ.get("ESKIZ_EMAIL")
ESKIZ_PASSWORD = os.environ.get("ESKIZ_PASSWORD")
ESKIZ_SENDER_NAME = os.environ.get("ESKIZ_SENDER_NAME", "4546")  # Eskiz's own shared default sender ID for accounts without a registered brand name
ESKIZ_API_BASE_URL = os.environ.get("ESKIZ_API_BASE_URL", "https://notify.eskiz.uz/api")
ESKIZ_TIMEOUT_SECONDS = float(os.environ.get("ESKIZ_TIMEOUT_SECONDS", "10"))

# Telegram Bot API gateway (Phase 04) -- see apps/notifications/infrastructure/gateways.py.
# "disabled" (the default) preserves the existing fail-loud NotImplementedTelegramGateway.
NUTRIZONE_TELEGRAM_GATEWAY = os.environ.get("NUTRIZONE_TELEGRAM_GATEWAY", "disabled")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME")  # Phase 4 Telegram automatic login: the bot's own @username for the https://t.me/<username>?start=<token> deep link
TELEGRAM_API_BASE_URL = os.environ.get("TELEGRAM_API_BASE_URL", "https://api.telegram.org")
TELEGRAM_TIMEOUT_SECONDS = float(os.environ.get("TELEGRAM_TIMEOUT_SECONDS", "10"))
# Phase 15B: validates the `X-Telegram-Bot-Api-Secret-Token` header Telegram sends
# on every webhook request when a secret_token was set via setWebhook -- this is
# Telegram's own supported webhook authentication mechanism, not a custom scheme.
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
# The backend's own public HTTPS origin (e.g. "https://api.nutrizone.uz"), no
# trailing slash -- used by `telegram_set_webhook` to build the full webhook
# URL Telegram should deliver updates to. Distinct from any frontend domain.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL")

# Street-level geocoding for the address form / dashboard (apps/geo/infrastructure/gateways/geocoder.py):
# OpenStreetMap Nominatim by default (free, ~1 req/s, identifying User-Agent required). Point GEOCODER_URL at a
# self-hosted Nominatim for higher volume; GEOCODER_ENABLED=0 turns street lookup off (city / region still work).
GEOCODER_ENABLED = os.environ.get("GEOCODER_ENABLED", "1") not in ("0", "false", "False")
GEOCODER_URL = os.environ.get("GEOCODER_URL", "https://nominatim.openstreetmap.org")
GEOCODER_USER_AGENT = os.environ.get("GEOCODER_USER_AGENT", "NutriZone/1.0 (+https://nutrizone.uz)")

# Fernet key (urlsafe base64, 32 bytes) encrypting payment-provider secrets stored from the Dashboard.
# Optional: derived from SECRET_KEY when unset -- set it in production so rotating SECRET_KEY keeps the secrets readable.
PAYMENT_SECRETS_KEY = os.environ.get("PAYMENT_SECRETS_KEY", "")
# The customer-facing Next.js storefront's own public origin (e.g.
# "https://nutrizone.uz"), distinct from PUBLIC_BASE_URL (the backend
# API's own origin) -- used to build the bot's "auto-login" deep link.
FRONTEND_URL = os.environ.get("FRONTEND_URL")
# Temporarily disabled per explicit product decision -- Telegram is
# now the sole customer-facing login path. Kept as a simple, reversible
# toggle (not a deletion) so SMS/phone+OTP login can be re-enabled
# later by flipping this one setting back to true -- no code changes
# needed. Does NOT affect /auth/verify-otp (shared with the Telegram
# 6-digit-code flow) or Telegram-specific endpoints.
NUTRIZONE_SMS_LOGIN_ENABLED = os.environ.get("NUTRIZONE_SMS_LOGIN_ENABLED", "false").lower() == "true"
# Opt-in only -- when true, TelegramBotConfig.ready() automatically
# calls `telegram_set_webhook` on real server startup (runserver/
# gunicorn/uwsgi/daphne/uvicorn only, never on migrate/test/shell).
# Off by default so no sandbox/CI/local-dev environment is ever
# surprised by an outbound Telegram API call.
TELEGRAM_AUTO_SET_WEBHOOK = os.environ.get("TELEGRAM_AUTO_SET_WEBHOOK", "false").lower() == "true"
# Phase 15E: the manager-facing Orders Channel/group chat_id -- new orders are posted here with inline confirm/cancel buttons.
TELEGRAM_ORDERS_CHAT_ID = os.environ.get("TELEGRAM_ORDERS_CHAT_ID")
# Phase 15 continuation: the staff-facing Orders Channel/group chat_id --
# a real Telegram group/channel chat_id is negative (Bot API convention);
# blank/unset means the Orders Channel notification feature stays inactive,
# never silently sending to a wrong or fabricated destination.
TELEGRAM_ORDERS_CHAT_ID = os.environ.get("TELEGRAM_ORDERS_CHAT_ID", "")

# Phase 15F: a genuinely separate second bot (its own @username/token, not
# a second destination chat for the same customer-facing bot -- explicit
# product decision) dedicated to the Orders Channel: it posts new orders
# and carries the Confirm/Cancel buttons (see orders_channel_subscriber.py
# and callback_router._handle_manager_action), on its own webhook route
# (/api/v1/telegram/orders-webhook) and its own secret, independent of the
# customer-facing bot's TELEGRAM_BOT_TOKEN/TELEGRAM_WEBHOOK_SECRET above.
TELEGRAM_ORDERS_BOT_TOKEN = os.environ.get("TELEGRAM_ORDERS_BOT_TOKEN")
TELEGRAM_ORDERS_BOT_USERNAME = os.environ.get("TELEGRAM_ORDERS_BOT_USERNAME")
TELEGRAM_ORDERS_WEBHOOK_SECRET = os.environ.get("TELEGRAM_ORDERS_WEBHOOK_SECRET")

# NutriZoneAnalyticsBot -- a third, management-only bot (apps/telegram_bot/infrastructure/analytics_bot.py): scheduled
# daily/weekly/monthly business reports, on-demand reports and unanswered-chat alerts. Webhook
# /api/v1/telegram/analytics-webhook. Only the comma-separated chat ids in TELEGRAM_ANALYTICS_CHAT_IDS get data.
TELEGRAM_ANALYTICS_BOT_TOKEN = os.environ.get("TELEGRAM_ANALYTICS_BOT_TOKEN")

# ---------------------------------------------------------------- AI shopping assistant (apps/assistant, Claude API)
# The Anthropic SDK reads ANTHROPIC_API_KEY itself; without it the assistant is off (the storefront hides it).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ASSISTANT_ENABLED = os.environ.get("ASSISTANT_ENABLED", "true").lower() in ("1", "true", "yes")
ASSISTANT_PROVIDER = os.environ.get("ASSISTANT_PROVIDER", "auto")  # auto: Claude when ANTHROPIC_API_KEY is set, else the free local advisor; "local" forces the advisor
ASSISTANT_MODEL = os.environ.get("ASSISTANT_MODEL", "claude-opus-5-5")
ASSISTANT_EFFORT = os.environ.get("ASSISTANT_EFFORT", "low")  # chat: low; raise to medium if answers need more care
ASSISTANT_MAX_TURNS = int(os.environ.get("ASSISTANT_MAX_TURNS", "30"))  # customer questions per conversation
ASSISTANT_RATE_PER_10_MIN = int(os.environ.get("ASSISTANT_RATE_PER_10_MIN", "20"))
ASSISTANT_RATE_PER_DAY = int(os.environ.get("ASSISTANT_RATE_PER_DAY", "150"))
# Read-aloud (apps/assistant/infrastructure/tts.py): Azure Speech has natural Uzbek voices (uz-UZ-MadinaNeural / SardorNeural).
AZURE_SPEECH_KEY = os.environ.get("AZURE_SPEECH_KEY", "")
AZURE_SPEECH_REGION = os.environ.get("AZURE_SPEECH_REGION", "")
ASSISTANT_TTS_VOICE_UZ = os.environ.get("ASSISTANT_TTS_VOICE_UZ", "")  # e.g. uz-UZ-SardorNeural for a male voice
ASSISTANT_TTS_VOICE_RU = os.environ.get("ASSISTANT_TTS_VOICE_RU", "")
ASSISTANT_TTS_VOICE_EN = os.environ.get("ASSISTANT_TTS_VOICE_EN", "")
ASSISTANT_TTS_RATE_PER_10_MIN = int(os.environ.get("ASSISTANT_TTS_RATE_PER_10_MIN", "40"))
TELEGRAM_ANALYTICS_BOT_USERNAME = os.environ.get("TELEGRAM_ANALYTICS_BOT_USERNAME", "NutriZoneAnalyticsBot")
TELEGRAM_ANALYTICS_WEBHOOK_SECRET = os.environ.get("TELEGRAM_ANALYTICS_WEBHOOK_SECRET")
TELEGRAM_ANALYTICS_CHAT_IDS = os.environ.get("TELEGRAM_ANALYTICS_CHAT_IDS", "")

# Loyalty programme: orders placed before this date still count towards a
# customer's tier (lifetime spend), but only orders placed on/after it earn
# coins -- so launching the programme never retro-credits old orders. Set to
# an empty string to reward every historical fulfilled order.
LOYALTY_EARN_SINCE = os.environ.get("LOYALTY_EARN_SINCE", "2026-09-27")
