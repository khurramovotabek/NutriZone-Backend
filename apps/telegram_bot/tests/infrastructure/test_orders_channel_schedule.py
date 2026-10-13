"""
Real, live-verified regression test: `telegram_bot.sync_orders_channel`
(see orders_channel_subscriber.py) was already fully implemented --
Confirm/Cancel buttons already drove real order status changes -- but
no `PeriodicTask` row ever existed for it, so Celery Beat's own
DB-backed scheduler (django_celery_beat.DatabaseScheduler) never
actually ran it. Migration 0004 closes that real, confirmed gap.
"""
from __future__ import annotations

import pytest
from django_celery_beat.models import PeriodicTask

pytestmark = pytest.mark.django_db


class TestOrdersChannelSchedule:
    def test_orders_channel_sync_is_scheduled_and_enabled(self):
        task = PeriodicTask.objects.get(name="Telegram Orders Channel sync")
        assert task.task == "telegram_bot.sync_orders_channel"
        assert task.enabled is True

    def test_orders_channel_sync_runs_every_30_seconds(self):
        task = PeriodicTask.objects.get(name="Telegram Orders Channel sync")
        assert task.interval is not None
        assert task.interval.every == 30
        assert task.interval.period == "seconds"
