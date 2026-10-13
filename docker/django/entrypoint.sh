#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] Waiting for PostgreSQL at ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
python scripts/wait_for_db.py

# Real, closed gap: migration is NO LONGER run here. Every app service
# (web, channels, every celery worker, celery beat) previously shared
# this exact entrypoint and each independently ran
# "python manage.py migrate" on its own startup -- several containers
# racing to create/alter the same tables at once, causing real
# PostgreSQL errors ("relation already exists", duplicate-key
# violations on Django's own internal sequences). Migration now runs
# exactly once, in the dedicated "migrate" service (see
# migrate-entrypoint.sh) -- every service below depends on it via
# `condition: service_completed_successfully` in docker-compose.yml,
# so by the time this script reaches `exec "$@"`, migrations are
# already guaranteed complete.

# Note: automatic Telegram webhook registration is NOT handled here.
# apps/telegram_bot/apps.py's own AppConfig.ready() already does this,
# gated behind TELEGRAM_AUTO_SET_WEBHOOK=true (off by default), and
# only for real server processes (runserver/gunicorn/etc, never
# migrate/test/shell) -- a second, unconditional copy of that logic
# here would be a real, duplicated code path.

echo "[entrypoint] Starting: $*"
exec "$@"
