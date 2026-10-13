"""
Celery configuration component (Django Implementation Blueprint §8).

Five queues mapped to business urgency, not to bounded context. Each
queue is intended to be consumed by a dedicated worker pool (a deploy-
time/docker-compose concern, see docker/compose/) so a burst of `bulk`
work can never starve `transactional` tasks.
"""
from __future__ import annotations

import os

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)

CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True

# Queue names, per Django Implementation Blueprint §8's queue table.
CELERY_TASK_QUEUES_NAMES = (
    "transactional",
    "inventory_critical",
    "default",
    "bulk",
    "scheduled",
    "dead_letter",
)
CELERY_TASK_DEFAULT_QUEUE = "default"

# Retry defaults -- per-task overrides live at the task decorator level
# once business tasks are written; these are the platform defaults.
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_DEFAULT_RETRY_DELAY = 10  # seconds, exponential backoff applied per-task
CELERY_TASK_MAX_RETRIES_DEFAULT = 5

# Celery Beat: schedule is database-backed (django-celery-beat) per
# Django Implementation Blueprint §8, NOT a hardcoded CELERYBEAT_SCHEDULE
# dict -- so the `scheduler.scheduled_jobs` Admin CRM screen reflects the
# real, editable schedule. No jobs are registered at foundation stage.
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True

CELERY_TASK_ROUTES = {
    # Populated per-task as business modules register their Celery tasks
    # (MIC §1 step 15). Left empty at foundation stage.
}
