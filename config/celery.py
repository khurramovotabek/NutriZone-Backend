"""
Celery application instance.

Five queues per Django Implementation Blueprint §8, each intended for a
dedicated worker pool (see docker/compose/ for the concrete `celery
worker -Q <queue>` service definitions) so `bulk` work can never starve
`transactional` tasks.
"""
import os

from celery import Celery
from kombu import Queue

os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"config.settings.{os.environ.get('DJANGO_ENV', 'development')}")

app = Celery("nutrizone")
app.config_from_object("django.conf:settings", namespace="CELERY")

app.conf.task_queues = (
    Queue("transactional"),
    Queue("inventory_critical"),
    Queue("default"),
    Queue("bulk"),
    Queue("scheduled"),
    Queue("dead_letter"),
)

# Discovers `infrastructure/tasks.py` in every one of this project's
# own local apps (rather than the Celery default of a top-level
# `tasks.py`), matching this project's layered app structure (Django
# Implementation Blueprint §3). Explicitly scoped to `LOCAL_APPS` --
# NOT the full `INSTALLED_APPS` -- confirmed as a genuine, real defect
# by direct execution: passing no `packages` argument makes Celery's
# Django integration scan every installed app, including Django's own
# built-ins and third-party apps (django.contrib.auth,
# rest_framework, django_celery_beat, etc.), none of which follow this
# project's `infrastructure/tasks.py` convention. With `force=True`
# this raised `ModuleNotFoundError: No module named
# 'django.contrib.auth.infrastructure'` outright; without `force`,
# Celery's lazy discovery silently found zero tasks project-wide, not
# just for apps lacking a tasks module. Scoping to `LOCAL_APPS`
# (already the project's own established list of its real bounded
# contexts) resolves both failure modes.
from django.conf import settings as _django_settings  # noqa: E402

app.autodiscover_tasks(packages=_django_settings.LOCAL_APPS, related_name="infrastructure.tasks")

# Propagates correlation_id/causation_id from the triggering
# HTTP request/event into every task executed by a worker
# (core/observability/middleware.py) -- "Background task metrics"
# requirement.
from core.observability.middleware import register_celery_correlation_signals  # noqa: E402

register_celery_correlation_signals()


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # pragma: no cover - manual diagnostic task only
    print(f"Request: {self.request!r}")
