"""
Every module's Outbox relay task must be on the beat schedule -- the relays existed
since launch but were never scheduled, so no event was ever delivered (operator
chat replies never reached the customer's Telegram).
"""
from __future__ import annotations

import pytest
from config.celery import app

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def test_every_relay_task_is_scheduled_every_minute():
    from django_celery_beat.models import PeriodicTask

    app.loader.import_default_modules()
    relays = {name for name in app.tasks if name.endswith(".relay_outbox_events")}
    assert relays, "no relay tasks registered"
    scheduled = {t.task: t for t in PeriodicTask.objects.filter(task__in=relays, enabled=True)}
    assert set(scheduled) == relays
    assert all(t.crontab and t.crontab.minute == "*" for t in scheduled.values())
