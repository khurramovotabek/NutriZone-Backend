from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone as django_timezone

from apps.notifications.infrastructure.repositories import DjangoNotificationRepository
from apps.notifications.infrastructure.tasks import flag_undelivered_notifications, rebuild_notification_statistics, relay_outbox_events
from apps.notifications.tests.factories import make_notification

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestCeleryTasks:
    def test_flag_undelivered_notifications_runs_without_error(self):
        assert isinstance(flag_undelivered_notifications(), int)

    def test_flag_undelivered_notifications_counts_seeded_stale_notification(self):
        """Seeds a deliberately old notification with zero delivery attempts and verifies the task actually counts it."""
        notification = make_notification(at=django_timezone.now() - timedelta(hours=2))
        DjangoNotificationRepository().save(notification)
        count = flag_undelivered_notifications()
        assert count >= 1

    def test_flag_undelivered_notifications_never_mutates_a_notification(self):
        """Verifies the disclosed read-only design documented in Phase 2: this task must never change a Notification's status or create a delivery, only report on it."""
        notification = make_notification()
        repo = DjangoNotificationRepository()
        repo.save(notification)
        flag_undelivered_notifications()
        fetched = repo.get_by_id(notification.id)
        assert fetched.status.value == "unseen"
        assert fetched.deliveries == {}

    def test_rebuild_notification_statistics_runs_without_error(self):
        assert rebuild_notification_statistics() == "ok"

    def test_relay_outbox_events_runs_without_error(self):
        result = relay_outbox_events()
        assert isinstance(result, dict)
