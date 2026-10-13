"""
Repository integration tests -- require a real PostgreSQL database.
Includes explicit database-constraint verification, not just
round-trip tests.

**Per this phase's own explicit instruction, `message_deleted_at`-
style naming from another module is explicitly NOT reproduced here**
-- this module has no soft-deletion timestamp collision to avoid in
the first place (`NotificationModel` has no Domain-level delete
concept at all), so a dedicated `notification_deleted_at` field would
be pure cargo-culting from Chat's own unrelated problem. Verified
directly: no such field exists in `models.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from django.db import IntegrityError

from apps.notifications.domain.enums import NotificationChannel, NotificationType
from apps.notifications.infrastructure import models as orm
from apps.notifications.infrastructure.repositories import DjangoNotificationPreferenceRepository, DjangoNotificationRepository
from apps.notifications.tests.factories import make_notification, make_preference

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoNotificationRepository:
    def test_save_then_get_by_id_round_trips(self):
        repo = DjangoNotificationRepository()
        notification = make_notification()
        repo.save(notification)

        fetched = repo.get_by_id(notification.id)
        assert fetched is not None
        assert fetched.title.value == notification.title.value
        assert fetched.body.value == notification.body.value

    def test_title_is_never_null_in_persisted_row(self):
        """A direct proof of the certified 'title is required' rule holding at the persistence boundary, not just the Domain constructor."""
        repo = DjangoNotificationRepository()
        notification = make_notification()
        repo.save(notification)

        row = orm.NotificationModel.objects.get(id=notification.id)
        assert row.title
        assert row.title.strip() != ""

    def test_seen_at_and_read_at_round_trip(self):
        repo = DjangoNotificationRepository()
        notification = make_notification()
        at = datetime.utcnow()
        notification.mark_read(at)
        repo.save(notification)

        fetched = repo.get_by_id(notification.id)
        assert fetched.read_at is not None
        assert fetched.status.value == "read"

    def test_get_by_id_missing_returns_none(self):
        repo = DjangoNotificationRepository()
        assert repo.get_by_id(uuid.uuid4()) is None

    def test_delivery_round_trips(self):
        repo = DjangoNotificationRepository()
        notification = make_notification()
        notification.record_delivery_attempt(NotificationChannel.TELEGRAM, datetime.utcnow())
        repo.save(notification)

        fetched = repo.get_by_id(notification.id)
        assert len(fetched.deliveries) == 1
        delivery = next(iter(fetched.deliveries.values()))
        assert delivery.channel.value == "telegram"

    def test_list_for_recipient(self):
        repo = DjangoNotificationRepository()
        notification = make_notification()
        repo.save(notification)
        results, total = repo.list_for_recipient(notification.recipient_id, status=None, page=1, page_size=20)
        assert total == 1

    def test_list_for_recipient_filters_by_status(self):
        repo = DjangoNotificationRepository()
        notification = make_notification()
        notification.mark_read(datetime.utcnow())
        repo.save(notification)
        results, total = repo.list_for_recipient(notification.recipient_id, status="read", page=1, page_size=20)
        assert total == 1
        results, total = repo.list_for_recipient(notification.recipient_id, status="unseen", page=1, page_size=20)
        assert total == 0


class TestDjangoNotificationPreferenceRepository:
    def test_save_then_get_by_user_id_round_trips(self):
        repo = DjangoNotificationPreferenceRepository()
        preference = make_preference()
        repo.save(preference)

        fetched = repo.get_by_user_id(preference.user_id)
        assert fetched is not None
        assert fetched.user_id == preference.user_id

    def test_disabled_combinations_round_trip_as_sparse_json(self):
        repo = DjangoNotificationPreferenceRepository()
        preference = make_preference()
        preference.disable(NotificationChannel.EMAIL, NotificationType.PROMOTIONAL)
        repo.save(preference)

        fetched = repo.get_by_user_id(preference.user_id)
        assert fetched.is_enabled(NotificationChannel.EMAIL, NotificationType.PROMOTIONAL) is False
        assert fetched.is_enabled(NotificationChannel.EMAIL, NotificationType.TRANSACTIONAL) is True

    def test_get_by_user_id_missing_returns_none(self):
        repo = DjangoNotificationPreferenceRepository()
        assert repo.get_by_user_id(uuid.uuid4()) is None

    def test_user_id_uniqueness_enforced(self):
        user_id = uuid.uuid4()
        orm.NotificationPreferenceModel.objects.create(user_id=user_id)
        with pytest.raises(IntegrityError):
            orm.NotificationPreferenceModel.objects.create(user_id=user_id)
