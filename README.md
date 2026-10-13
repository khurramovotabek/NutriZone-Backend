# NutriZone Backend

Premium Sport Nutrition & Vitamins Platform — Enterprise Django 6 Backend

**Production-oriented, feature-complete backend.** This is no longer a
foundation-only scaffold — every module listed below is real, tested,
and connected end-to-end (Telegram bot, storefront API, and Admin
Dashboard all consume it live).

## What's implemented

- **Identity & Authentication** — Telegram-based, passwordless login
  (bot onboarding, 6-digit OTP, automatic-login deep links), JWT
  access/refresh tokens, session management, profile (including
  username, avatar upload).
- **Products & Catalog** — categories, brands, variants, attributes,
  multilingual content (UZ/RU/EN) for every translatable field, media
  pipeline (images/video), manufacturer/country-of-origin/expiry-date
  fields.
- **Pricing** — price lists, campaigns, coupons (percentage/fixed,
  stacking rules), quantity tiers, price snapshots for checkout
  integrity.
- **Cart** — full guest (anonymous, token-based) and authenticated
  cart support; only checkout itself requires a logged-in session.
- **Ordering** — order lifecycle, returns, cancellations; Telegram bot
  checkout with real delivery-location capture.
- **Inventory** — stock tracking, now managed directly from the
  Product admin form (a dedicated multi-page Inventory workspace was
  deliberately removed from the Dashboard for simplicity — the
  underlying data model is untouched).
- **POS (Point of Sale)** — a premium, liquid-glass Django Dashboard
  terminal: barcode/SKU search, cart, promo codes (real backend
  discount calculation, no client-side faking), cash checkout,
  itemized/printable receipts.
- **Reviews** — customer reviews with moderation workflow and media.
- **Chat** — real-time customer support conversations, Telegram
  bot integration.
- **Notifications** — Telegram delivery gateway, in-app notifications.
- **Geo** — countries (with flag icons), regions, cities, addresses
  (with recipient name/phone/Telegram username for checkout).
- **Telegram Bot** — full customer-facing assistant: registration,
  login codes, catalog browsing, cart, checkout, order history,
  support chat — all routed through this same backend, never a
  second, divergent business-logic implementation.
- **Admin Dashboard** (`/django-admin/`) — django-jazzmin based,
  liquid-glass themed, fully translated (UZ/RU/EN) including field
  labels and section headers, simplified to hide internal/read-only
  data (event logs, audit trails) that a store manager never edits by
  hand.

## Modules deliberately removed

Loyalty, Wallet, Store (warehouses/branches/delivery-zone management),
and Fulfillment (shipment/delivery-attempt tracking) were fully
removed — backend code, frontend references, Dashboard admin pages,
and orphaned database tables all cleaned up via dedicated migrations.
Core commerce (Pricing, Cart, Checkout, POS, Telegram bot, Products,
Reviews) remains fully intact.

## Requirements

- Docker + Docker Compose v2
- (For non-Docker local dev) Python 3.12+, PostgreSQL 16, Redis 7

## Quick start (Docker)

```bash
cp .env.example .env.local
# edit .env.local: at minimum set SECRET_KEY, JWT_SIGNING_KEY, and POSTGRES_PASSWORD.
# For real Telegram login/bot functionality, also set TELEGRAM_BOT_TOKEN,
# TELEGRAM_WEBHOOK_SECRET, PUBLIC_BASE_URL, and NUTRIZONE_TELEGRAM_GATEWAY=live.

docker compose -f docker/compose/docker-compose.yml up --build
```

Migrations run exactly once, in a dedicated `migrate` service that
every other service (`web`, `channels`, all Celery workers/beat)
depends on via Docker Compose's own `service_completed_successfully`
condition — no more per-container migration races.

The Telegram webhook registers itself automatically on `web`'s own
startup when `TELEGRAM_AUTO_SET_WEBHOOK=true` (off by default; see
`.env.example`) — `channels` and Celery services never attempt this,
avoiding Telegram's own "Too Many Requests" rejection for duplicate
registration.

Once the stack is up:

- API root: <http://localhost/api/v1/>
- Swagger UI: <http://localhost/api/docs/swagger/>
- ReDoc: <http://localhost/api/docs/redoc/>
- Liveness: <http://localhost/health/live>
- Readiness: <http://localhost/health/ready>
- Django Admin Dashboard: <http://localhost/django-admin/>

Create a superuser for Dashboard access:

```bash
docker compose -f docker/compose/docker-compose.yml exec web python manage.py createsuperuser
```

## Repository layout

| Directory | Contents |
|---|---|
| `apps/` | One Django app per bounded context, each following the Universal Module Implementation Contract folder structure |
| `config/` | Settings, URL roots, ASGI/WSGI/Celery entrypoints, Jazzmin (Dashboard) configuration |
| `common/` | Framework-adjacent reusable building blocks (base models, pagination, permissions, response envelope, exceptions, locale choices) |
| `core/` | Platform infrastructure (Outbox, event registry, storage abstraction, caching, idempotency, health checks, media pipeline) |
| `docker/` | Dockerfile, docker-compose (dev/prod), entrypoint scripts |
| `locale/` | UZ/RU translations for the Dashboard's own UI (field labels, section headers) — separate from the storefront's own next-intl translations |
| `templates/admin/` | Dashboard customizations (POS terminal, reports) — the only server-rendered HTML in this repository; everything customer-facing is the separate Next.js storefront |
| `tests/` | Cross-app integration/contract tests only (per-app tests live inside each app) |

## Running tests

```bash
docker compose -f docker/compose/docker-compose.yml exec web pytest
```

The full suite (3,900+ tests across every app) passes cleanly and is
re-run twice after any change in this codebase's own development
discipline, to catch order-dependent flakiness before it ships.

## Code quality

```bash
docker compose -f docker/compose/docker-compose.yml exec web ruff check .
docker compose -f docker/compose/docker-compose.yml exec web ruff format --check .
docker compose -f docker/compose/docker-compose.yml exec web mypy .
```

## Internationalization

The Dashboard (`/django-admin/`) supports UZ/RU/EN via Django's own
`gettext`/`.po` files under `locale/` — this covers field labels,
section headers, and other admin-chrome text. If you add a new
`verbose_name`, `help_text`, or `fieldsets` label anywhere in
`apps/*/infrastructure/admin.py` or `models.py`, regenerate and fill
in translations:

```bash
python manage.py makemessages -l uz -l ru --no-obsolete
# translate any new, empty msgstr entries in locale/{uz,ru}/LC_MESSAGES/django.po
python manage.py compilemessages
```

The customer-facing storefront (Next.js) uses its own, separate
next-intl translation files — see `nutrizone-storefront/README.md`.

## What's deliberately *not* here

- A second, business-facing admin CRM frontend — the Dashboard
  (`/django-admin/`) and the POS terminal are the real, production
  management surfaces; there is no separate React admin app.
- Card/other electronic payment methods in POS — the `Sale` domain
  model only supports cash; adding electronic payment methods is a
  real backend/domain change, not a frontend styling decision.
- Warehouse/branch management — removed with the Store module; POS
  stock tracking uses a single, well-known default location.
