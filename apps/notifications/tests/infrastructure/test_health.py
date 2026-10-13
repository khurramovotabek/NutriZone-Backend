from __future__ import annotations

import uuid

import pytest
from django.db import connection

from apps.notifications.infrastructure import models as orm
from apps.notifications.infrastructure.health import (
    check_composition_integrity,
    check_notification_cache,
    check_notification_content_integrity,
    check_notification_outbox_backlog,
    check_notification_repository,
    check_orphaned_deliveries,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestHealthChecks:
    def test_check_notification_repository_healthy(self):
        ok, detail = check_notification_repository()
        assert ok is True

    def test_check_notification_outbox_backlog_reports_count(self):
        ok, detail = check_notification_outbox_backlog()
        assert ok is True
        assert "pending" in detail

    def test_check_orphaned_deliveries_healthy_by_default(self):
        ok, detail = check_orphaned_deliveries()
        assert ok is True

    def test_check_notification_content_integrity_healthy_by_default(self):
        ok, detail = check_notification_content_integrity()
        assert ok is True

    def test_check_notification_content_integrity_flags_seeded_empty_title(self):
        """Seeds a deliberately invalid row with an empty title (bypassing the aggregate's own EmptyNotificationContent check via raw ORM creation) and verifies the health check actually catches it."""
        orm.NotificationModel.objects.create(recipient_id=uuid.uuid4(), notification_type="transactional", title="placeholder", body="x")
        row = orm.NotificationModel.objects.filter(body="x").first()
        with connection.cursor() as cursor:
            cursor.execute("UPDATE notifications_notifications SET title = '' WHERE id = %s", [str(row.id)])
        ok, detail = check_notification_content_integrity()
        assert ok is False

    def test_check_composition_integrity_healthy(self):
        ok, detail = check_composition_integrity()
        assert ok is True

    def test_check_notification_cache_round_trips(self):
        ok, detail = check_notification_cache()
        assert ok is True
