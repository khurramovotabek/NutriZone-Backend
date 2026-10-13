"""
**POS' `event_handlers.py` has no `CACHE_GROUPS`/`invalidate_*`
mechanism at all** -- a real, disclosed departure matching Analytics'
own identical, disclosed departure, since zero selectors exist to
invalidate. Tests here verify only metrics dispatch, matching that
certified reality.
"""
from __future__ import annotations

import ast

import pytest

import apps.pos.domain.events as events_module
import apps.pos.infrastructure.event_handlers as handlers_module
from apps.pos.infrastructure.event_handlers import _EVENT_TO_METRIC, handle_pos_event

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestEventHandlerDispatch:
    def test_handle_sale_opened_does_not_raise(self):
        handle_pos_event("SaleOpened", {"sale_id": "x"})

    def test_handle_unknown_event_is_a_noop(self):
        handle_pos_event("SomeUnregisteredEvent", {})

    def test_all_6_events_mapped_to_a_metric(self):
        tree = ast.parse(open(events_module.__file__).read())
        domain_events = set(n.name for n in tree.body if isinstance(n, ast.ClassDef))
        mapped = set(_EVENT_TO_METRIC.keys())
        assert domain_events == mapped, f"Mismatch: {domain_events.symmetric_difference(mapped)}"

    def test_all_6_events_registered_in_event_contracts(self):
        tree = ast.parse(open(events_module.__file__).read())
        domain_events = set(n.name for n in tree.body if isinstance(n, ast.ClassDef))

        with open("shared/event_contracts/pos.py") as f:
            contract_tree = ast.parse(f.read())
        registered = set(n.elts[0].value for n in ast.walk(contract_tree) if isinstance(n, ast.Tuple) and len(n.elts) == 2 and isinstance(n.elts[0], ast.Constant))
        assert domain_events == registered, f"Mismatch: {domain_events.symmetric_difference(registered)}"

    def test_zero_cache_group_mechanism_exists(self):
        """A direct, executable proof of the disclosed departure this module's own event_handlers.py documents."""
        assert not hasattr(handlers_module, "CACHE_GROUPS")
        assert not hasattr(handlers_module, "invalidate_pos_cache_group")
