from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.clock import Clock
from core.observability import correlation_scope
from core.outbox import EventEnvelope

pytestmark = pytest.mark.unit


def test_build_produces_a_unique_event_id():
    a = EventEnvelope.build("ProductCreated", payload={})
    b = EventEnvelope.build("ProductCreated", payload={})
    assert a.event_id != b.event_id


def test_build_defaults_to_version_one():
    envelope = EventEnvelope.build("ProductCreated", payload={})
    assert envelope.event_version == 1


def test_build_respects_explicit_version():
    envelope = EventEnvelope.build("ProductCreated", payload={}, event_version=3)
    assert envelope.event_version == 3


def test_build_uses_clock_for_occurred_at():
    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with Clock.freeze(fixed):
        envelope = EventEnvelope.build("ProductCreated", payload={})
    assert envelope.occurred_at == fixed.isoformat()


def test_build_picks_up_active_correlation_scope():
    with correlation_scope(correlation_id="corr-1", causation_id="caus-1"):
        envelope = EventEnvelope.build("OrderPlaced", payload={"order_id": "o1"})
    assert envelope.correlation_id == "corr-1"
    assert envelope.causation_id == "caus-1"


def test_build_explicit_correlation_overrides_context():
    with correlation_scope(correlation_id="context-corr"):
        envelope = EventEnvelope.build("OrderPlaced", payload={}, correlation_id="explicit-corr")
    assert envelope.correlation_id == "explicit-corr"


def test_build_with_no_active_scope_has_none_correlation():
    envelope = EventEnvelope.build("OrderPlaced", payload={})
    assert envelope.correlation_id is None
    assert envelope.causation_id is None


def test_payload_is_preserved_exactly():
    payload = {"order_id": "o1", "total": 100}
    envelope = EventEnvelope.build("OrderPlaced", payload=payload)
    assert envelope.payload == payload


def test_to_dict_includes_all_fields():
    envelope = EventEnvelope.build("OrderPlaced", payload={"a": 1}, metadata={"source": "web"})
    as_dict = envelope.to_dict()
    assert as_dict["event_type"] == "OrderPlaced"
    assert as_dict["payload"] == {"a": 1}
    assert as_dict["metadata"] == {"source": "web"}
    assert "event_id" in as_dict
    assert "occurred_at" in as_dict
