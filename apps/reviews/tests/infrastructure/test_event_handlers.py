from __future__ import annotations

import ast

import pytest

import apps.reviews.domain.events as events_module
from apps.reviews.infrastructure.event_handlers import CACHE_GROUPS, _EVENT_TO_CACHE_GROUPS, handle_review_event, invalidate_review_cache_group

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestCacheGroupInvalidation:
    def test_rejects_unknown_group(self):
        with pytest.raises(ValueError):
            invalidate_review_cache_group("not_a_real_group")

    def test_all_three_cache_groups_present(self):
        assert len(CACHE_GROUPS) == 3

    def test_invalidate_group_does_not_raise(self):
        invalidate_review_cache_group("review_detail")


class TestEventHandlerDispatch:
    def test_handle_review_created_does_not_raise(self):
        handle_review_event("ReviewCreated", {"review_id": "x"})

    def test_handle_unknown_event_is_a_noop(self):
        handle_review_event("SomeUnregisteredEvent", {})

    def test_all_9_events_dispatched(self):
        """Cross-checks the dispatch table against domain/events.py directly."""
        tree = ast.parse(open(events_module.__file__).read())
        domain_events = set(n.name for n in tree.body if isinstance(n, ast.ClassDef))
        dispatched = set(_EVENT_TO_CACHE_GROUPS.keys())
        assert domain_events == dispatched, f"Mismatch: {domain_events.symmetric_difference(dispatched)}"

    def test_all_9_events_registered(self):
        """Cross-checks shared/event_contracts/reviews.py against domain/events.py directly -- fresh AST parse, not a reused count."""
        tree = ast.parse(open(events_module.__file__).read())
        domain_events = set(n.name for n in tree.body if isinstance(n, ast.ClassDef))

        with open("shared/event_contracts/reviews.py") as f:
            contract_tree = ast.parse(f.read())
        registered = set(n.elts[0].value for n in ast.walk(contract_tree) if isinstance(n, ast.Tuple) and len(n.elts) == 2 and isinstance(n.elts[0], ast.Constant))
        assert domain_events == registered, f"Mismatch: {domain_events.symmetric_difference(registered)}"
