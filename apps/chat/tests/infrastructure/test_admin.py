from __future__ import annotations

import pytest
from django.contrib import admin

from apps.chat.infrastructure import models as orm

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoAdmin:
    def test_both_remaining_admin_registrations_present(self):
        """ChatOutboxEvent removed from the Dashboard (see test_outbox_event_removed_from_dashboard) -- only the two customer-facing models remain."""
        expected = [orm.ConversationModel, orm.MessageModel]
        for model in expected:
            assert model in admin.site._registry, f"{model.__name__} is not registered in admin"

    def test_messages_are_read_only_on_the_dashboard(self):
        """A message is the customer's (or operator's) own words and no Application Service edits or deletes one, so the register is view-only -- replies are written in the Chat markazi desk."""
        admin_cls = admin.site._registry[orm.MessageModel].__class__
        assert {"has_add_permission", "has_change_permission", "has_delete_permission"} <= set(admin_cls.__dict__)

    def test_outbox_event_removed_from_dashboard(self):
        """Real, product-required simplification: ChatOutboxEvent removed from the Dashboard entirely -- read-only, system-internal event-log data."""
        assert orm.ChatOutboxEvent not in admin.site._registry

    def test_conversation_bulk_actions_use_the_services(self):
        """Close / reopen / archive now exist as Application Services; the bulk actions call them (never a raw status write)."""
        admin_instance = admin.site._registry[orm.ConversationModel]
        assert set(admin_instance.actions) == {"close_selected", "reopen_selected", "archive_selected"}
        import inspect

        source = inspect.getsource(admin_instance.__class__._bulk)
        assert "composition" in source and ".update(" not in source
