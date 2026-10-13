"""
Application-layer tests for Notifications.

**Honest disclosure, re-verified fresh in this phase's own Step 1: 0
Application Services exist for Notifications.** No service test file
exists because there is nothing to test; fabricating one would
misrepresent real coverage.
"""
from __future__ import annotations

import pathlib
import uuid

import pytest

from apps.notifications.application.ports import NotificationPreferenceRepository, NotificationRepository
from apps.notifications.tests.application.fakes import FakeNotificationPreferenceRepository, FakeNotificationRepository
from apps.notifications.tests.factories import make_notification, make_preference

pytestmark = pytest.mark.unit


def test_notifications_application_services_now_exist():
    """A direct, executable statement of this module's real, current state (Phase 02G closed the previously-real 'zero Application Services' gap) -- replaces the old zero-files canary, which is no longer true."""
    services_dir = pathlib.Path("apps/notifications/application/services")
    service_files = [f for f in services_dir.glob("*.py") if f.name not in ("__init__.py", "_shared.py")]
    assert len(service_files) >= 1, "Expected at least one real Application Service file to exist."


class TestFakeNotificationRepositoryContract:
    def test_fake_satisfies_port_method_set(self):
        port_methods = {name for name in dir(NotificationRepository) if not name.startswith("_")}
        fake_methods = {name for name in dir(FakeNotificationRepository) if not name.startswith("_")}
        missing = port_methods - fake_methods
        assert not missing, f"FakeNotificationRepository is missing Port methods: {missing}"

    def test_save_then_get_by_id_round_trips(self):
        repo = FakeNotificationRepository()
        notification = make_notification()
        repo.save(notification)
        assert repo.get_by_id(notification.id) is notification

    def test_get_by_id_missing_returns_none(self):
        repo = FakeNotificationRepository()
        assert repo.get_by_id(uuid.uuid4()) is None

    def test_list_for_recipient_filters_by_status(self):
        repo = FakeNotificationRepository()
        notification = make_notification()
        repo.save(notification)
        results, total = repo.list_for_recipient(notification.recipient_id, status="unseen", page=1, page_size=20)
        assert total == 1
        results, total = repo.list_for_recipient(notification.recipient_id, status="read", page=1, page_size=20)
        assert total == 0


class TestFakeNotificationPreferenceRepositoryContract:
    def test_fake_satisfies_port_method_set(self):
        port_methods = {name for name in dir(NotificationPreferenceRepository) if not name.startswith("_")}
        fake_methods = {name for name in dir(FakeNotificationPreferenceRepository) if not name.startswith("_")}
        missing = port_methods - fake_methods
        assert not missing, f"FakeNotificationPreferenceRepository is missing Port methods: {missing}"

    def test_save_then_get_by_user_id_round_trips(self):
        repo = FakeNotificationPreferenceRepository()
        preference = make_preference()
        repo.save(preference)
        assert repo.get_by_user_id(preference.user_id) is preference

    def test_get_by_user_id_missing_returns_none(self):
        repo = FakeNotificationPreferenceRepository()
        assert repo.get_by_user_id(uuid.uuid4()) is None
