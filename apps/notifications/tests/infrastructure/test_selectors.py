from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from apps.notifications.infrastructure.repositories import DjangoNotificationRepository
from apps.notifications.infrastructure.selectors import NotificationSelector, NotificationStatisticsSelector
from apps.notifications.tests.factories import make_notification

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestNotificationSelector:
    def test_list_for_recipient(self):
        notification = make_notification()
        DjangoNotificationRepository().save(notification)
        results, total = NotificationSelector().list_for_recipient(notification.recipient_id, status=None, page=1, page_size=20)
        assert total == 1
        assert results[0]["id"] == str(notification.id)

    def test_list_for_recipient_filters_by_status(self):
        notification = make_notification()
        notification.mark_seen(datetime.utcnow())
        DjangoNotificationRepository().save(notification)
        results, total = NotificationSelector().list_for_recipient(notification.recipient_id, status="seen", page=1, page_size=20)
        assert total == 1
        results, total = NotificationSelector().list_for_recipient(notification.recipient_id, status="read", page=1, page_size=20)
        assert total == 0

    def test_list_for_recipient_empty_result(self):
        results, total = NotificationSelector().list_for_recipient(uuid.uuid4(), status=None, page=1, page_size=20)
        assert total == 0
        assert results == []


class TestNotificationStatisticsSelector:
    def test_counts_by_status_scoped_to_recipient(self):
        notification = make_notification()
        DjangoNotificationRepository().save(notification)
        counts = NotificationStatisticsSelector().counts_by_status(recipient_id=notification.recipient_id)
        assert counts.get("unseen", 0) == 1

    def test_counts_by_status_scoping_excludes_other_recipients(self):
        notification = make_notification()
        DjangoNotificationRepository().save(notification)
        counts = NotificationStatisticsSelector().counts_by_status(recipient_id=uuid.uuid4())
        assert counts == {}

    def test_counts_by_status_without_recipient_scope_is_platform_wide(self):
        notification = make_notification()
        DjangoNotificationRepository().save(notification)
        counts = NotificationStatisticsSelector().counts_by_status()
        assert counts.get("unseen", 0) >= 1
