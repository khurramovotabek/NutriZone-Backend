#!/usr/bin/env bash
set -euo pipefail

# Real, closed gap: this is the ONLY place "python manage.py migrate"
# runs anywhere in this project's Docker setup. Previously, every
# single app service (web, channels, celery_worker_transactional,
# celery_worker_default, celery_worker_bulk, celery_beat) shared one
# entrypoint that unconditionally ran migrate on its own container
# startup -- with 6 containers starting close together, several would
# race to migrate the same database at once, producing real
# PostgreSQL errors (duplicate relations, duplicate sequence/constraint
# names). This dedicated, single-purpose service runs to completion
# and exits; every other service's `depends_on` entry in
# docker-compose.yml uses `condition: service_completed_successfully`
# against this service, so Docker Compose itself guarantees migration
# finishes -- exactly once -- before any app service starts at all.

echo "[migrate] Waiting for PostgreSQL at ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
python scripts/wait_for_db.py

echo "[migrate] Running migrate..."
python manage.py migrate --noinput

if [ "${DJANGO_ENV:-development}" = "production" ]; then
    echo "[migrate] Collecting static files..."
    python manage.py collectstatic --noinput
fi

echo "[migrate] Migration complete."
