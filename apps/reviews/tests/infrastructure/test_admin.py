from __future__ import annotations

import pytest
from django.contrib import admin

from apps.reviews.infrastructure import models as orm

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoAdmin:
    def test_both_remaining_admin_registrations_present(self):
        """ReviewOutboxEvent removed from the Dashboard (see test_outbox_event_removed_from_dashboard) -- only the two customer-facing models remain."""
        expected = [orm.ReviewModel, orm.ReviewMediaModel]
        for model in expected:
            assert model in admin.site._registry, f"{model.__name__} is not registered in admin"

    def test_review_media_admin_is_read_only(self):
        admin_instance = admin.site._registry[orm.ReviewMediaModel]
        assert admin_instance.has_add_permission(None) is False
        assert admin_instance.has_change_permission(None) is False
        assert admin_instance.has_delete_permission(None) is False

    def test_outbox_event_removed_from_dashboard(self):
        """Real, product-required simplification: ReviewOutboxEvent removed from the Dashboard entirely -- read-only, system-internal event-log data."""
        assert orm.ReviewOutboxEvent not in admin.site._registry

    def test_bulk_moderation_actions_go_through_the_services(self, monkeypatch):
        """The moderation actions exist now that Approve/Publish/Reject/Hide services back them -- each one calls `moderate()`, never a raw status write."""
        from apps.reviews.infrastructure import admin as review_admin

        admin_instance = admin.site._registry[orm.ReviewModel]
        assert set(admin_instance.actions) == {"approve_selected", "reject_spam", "reject_offensive", "reject_off_topic", "hide_complaint"}
        calls = []
        monkeypatch.setattr(review_admin, "moderate", lambda pk, action, reason="": calls.append((action, reason)))
        admin_instance.message_user = lambda *a, **k: None
        admin_instance.reject_spam(None, [type("R", (), {"pk": 1})()])
        assert calls == [("reject", "spam")]
