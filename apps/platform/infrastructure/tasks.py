"""
apps/platform/infrastructure/tasks.py

Phase 02B's idempotency-record cleanup task. Reuses this project's
own already-proven Celery infrastructure (task discovery scoped to
LOCAL_APPS, confirmed working end-to-end via a real separate
worker/beat process pair in Phase 01C) rather than introducing any
new scheduling mechanism.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone as django_timezone


@shared_task(queue="maintenance", name="platform.cleanup_expired_idempotency_records")
def cleanup_expired_idempotency_records() -> dict:
    """
    Deletes IdempotencyRecord rows past their own expires_at. Safe to
    run repeatedly and safe to run concurrently with itself (a plain
    bulk DELETE ... WHERE expires_at < now(), no read-then-write race
    to worry about -- deleting an already-deleted row is a no-op, not
    an error). Intended to be registered as a periodic task via
    django_celery_beat (the same DatabaseScheduler proven working in
    Phase 01C), not scheduled by this module itself.
    """
    from apps.platform.infrastructure.models import IdempotencyRecord

    deleted_count, _ = IdempotencyRecord.objects.filter(expires_at__lt=django_timezone.now()).delete()
    return {"deleted": deleted_count}


@shared_task(queue="default", name="platform.control_scan")
def control_scan() -> dict:
    """Every 2 min (beat, migration 0019): the control centre's rules, then Telegram for the new findings."""
    from apps.platform.infrastructure import control_center

    return control_center.run()
