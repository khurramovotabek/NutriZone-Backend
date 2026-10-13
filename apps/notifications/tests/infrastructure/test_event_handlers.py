from __future__ import annotations

import ast

import pytest

import apps.notifications.domain.events as events_module
from apps.notifications.infrastructure.event_handlers import CACHE_GROUPS, _EVENT_TO_CACHE_GROUPS, handle_notification_event, invalidate_notification_cache_group

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestCacheGroupInvalidation:
    def test_rejects_unknown_group(self):
        with pytest.raises(ValueError):
            invalidate_notification_cache_group("not_a_real_group")

    def test_both_cache_groups_present(self):
        assert len(CACHE_GROUPS) == 2

    def test_invalidate_group_does_not_raise(self):
        invalidate_notification_cache_group("notification_list")


class TestEventHandlerDispatch:
    def test_handle_notification_created_does_not_raise(self):
        handle_notification_event("NotificationCreated", {"notification_id": "x"})

    def test_handle_unknown_event_is_a_noop(self):
        handle_notification_event("SomeUnregisteredEvent", {})

    def test_delivery_sent_and_channel_events_registered_with_empty_cache_groups(self):
        """Verifies the deliberate design disclosed in Phase 2: NotificationDeliverySent/ChannelEnabled/ChannelDisabled are registered but map to no cache invalidation, since no selector currently surfaces per-delivery or per-channel-preference state."""
        assert _EVENT_TO_CACHE_GROUPS["NotificationDeliverySent"] == ()
        assert _EVENT_TO_CACHE_GROUPS["NotificationChannelEnabled"] == ()
        assert _EVENT_TO_CACHE_GROUPS["NotificationChannelDisabled"] == ()

    def test_handle_delivery_sent_does_not_raise_despite_empty_cache_groups(self):
        handle_notification_event("NotificationDeliverySent", {"notification_id": "x"})

    def test_all_9_events_dispatched(self):
        tree = ast.parse(open(events_module.__file__).read())
        domain_events = set(n.name for n in tree.body if isinstance(n, ast.ClassDef))
        dispatched = set(_EVENT_TO_CACHE_GROUPS.keys())
        assert domain_events == dispatched, f"Mismatch: {domain_events.symmetric_difference(dispatched)}"

    def test_all_9_events_registered(self):
        tree = ast.parse(open(events_module.__file__).read())
        domain_events = set(n.name for n in tree.body if isinstance(n, ast.ClassDef))

        with open("shared/event_contracts/notifications.py") as f:
            contract_tree = ast.parse(f.read())
        registered = set(n.elts[0].value for n in ast.walk(contract_tree) if isinstance(n, ast.Tuple) and len(n.elts) == 2 and isinstance(n.elts[0], ast.Constant))
        assert domain_events == registered, f"Mismatch: {domain_events.symmetric_difference(registered)}"
