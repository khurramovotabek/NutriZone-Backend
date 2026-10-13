from __future__ import annotations

import pytest
from django.contrib import admin

from apps.notifications.infrastructure import models as orm

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoAdmin:
    def test_notification_model_registered(self):
        """NotificationOutboxEvent and NotificationPreferenceModel removed from the Dashboard (see test_outbox_event_removed_from_dashboard / test_notification_preference_removed_from_dashboard) -- only the customer-facing NotificationModel remains."""
        assert orm.NotificationModel in admin.site._registry, "NotificationModel is not registered in admin"

    def test_notification_history_is_read_only_and_new_messages_go_through_the_composer(self):
        """The list is the delivery history; writing a message happens in Dashboard → Xabar yuborish (nz_notify_send), which
        localizes it, picks an audience and optionally sends Telegram -- so the raw add/change forms are closed."""
        from django.urls import reverse

        admin_instance = admin.site._registry[orm.NotificationModel]
        assert admin_instance.has_add_permission(None) is False
        assert admin_instance.has_change_permission(None) is False
        assert "has_delete_permission" not in admin_instance.__class__.__dict__
        assert reverse("admin:nz_notify_send") == "/django-admin/notifications/send/"

    def test_outbox_event_removed_from_dashboard(self):
        """Real, product-required simplification: NotificationOutboxEvent removed from the Dashboard entirely -- read-only, system-internal event-log data."""
        assert orm.NotificationOutboxEvent not in admin.site._registry

    def test_notification_preference_removed_from_dashboard(self):
        """Real, product-required simplification: NotificationPreferenceModel removed from the Dashboard entirely -- backend-managed opt-out state an operator never edits by hand. Still backed by a real repository, just not exposed here."""
        assert orm.NotificationPreferenceModel not in admin.site._registry

    def test_bulk_actions_are_mark_read_and_hide(self):
        """Two plain inbox operations (no fabricated Application Service): mark as read, and hide from the customer's inbox."""
        admin_instance = admin.site._registry[orm.NotificationModel]
        assert set(admin_instance.actions) == {"mark_read", "cancel_selected"}
