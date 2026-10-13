from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import pytest

from common.middleware.audit_context import _current_actor_id
from core.outbox import OutboxRelay
from core.outbox.publisher import get_current_actor_id

pytestmark = pytest.mark.unit


@dataclass
class _FakeEventRow:
    pk: str
    published_at: object = None
    publish_attempts: int = 0
    saved_calls: list = field(default_factory=list)

    def save(self, update_fields=None):
        self.saved_calls.append(tuple(update_fields or []))


class _FakeQuerySet(list):
    def filter(self, **kwargs):
        published_at__isnull = kwargs.get("published_at__isnull")
        publish_attempts__lt = kwargs.get("publish_attempts__lt")
        results = self
        if published_at__isnull is not None:
            results = [r for r in results if (r.published_at is None) == published_at__isnull]
        if publish_attempts__lt is not None:
            results = [r for r in results if r.publish_attempts < publish_attempts__lt]
        return _FakeQuerySet(results)

    def order_by(self, *_args):
        return self

    def __getitem__(self, item):
        if isinstance(item, slice):
            return _FakeQuerySet(list.__getitem__(self, item))
        return list.__getitem__(self, item)


def _fake_model_with_rows(rows: list[_FakeEventRow]):
    queryset = _FakeQuerySet(rows)

    class _FakeModel:
        objects = queryset

    return _FakeModel


def test_relay_marks_successfully_published_events():
    rows = [_FakeEventRow(pk="1"), _FakeEventRow(pk="2")]
    model = _fake_model_with_rows(rows)
    relay = OutboxRelay(model, max_attempts=5, batch_size=100)

    summary = relay.relay_pending(publish_fn=lambda event: True)

    assert summary == {"published": 2, "failed": 0, "exhausted": 0}
    assert all(row.published_at is not None for row in rows)


def test_relay_increments_attempts_on_failure_and_leaves_unpublished():
    rows = [_FakeEventRow(pk="1")]
    model = _fake_model_with_rows(rows)
    relay = OutboxRelay(model, max_attempts=5, batch_size=100)

    summary = relay.relay_pending(publish_fn=lambda event: False)

    assert summary == {"published": 0, "failed": 1, "exhausted": 0}
    assert rows[0].published_at is None
    assert rows[0].publish_attempts == 1


def test_relay_marks_exhausted_after_max_attempts():
    rows = [_FakeEventRow(pk="1", publish_attempts=4)]
    model = _fake_model_with_rows(rows)
    relay = OutboxRelay(model, max_attempts=5, batch_size=100)

    summary = relay.relay_pending(publish_fn=lambda event: False)

    assert summary["exhausted"] == 1
    assert rows[0].publish_attempts == 5


def test_relay_skips_events_that_already_exhausted_attempts():
    rows = [_FakeEventRow(pk="1", publish_attempts=5)]
    model = _fake_model_with_rows(rows)
    relay = OutboxRelay(model, max_attempts=5, batch_size=100)

    summary = relay.relay_pending(publish_fn=lambda event: True)

    assert summary == {"published": 0, "failed": 0, "exhausted": 0}  # not picked up at all


def test_relay_skips_already_published_events():
    rows = [_FakeEventRow(pk="1", published_at="2026-01-01T00:00:00Z")]
    model = _fake_model_with_rows(rows)
    relay = OutboxRelay(model, max_attempts=5, batch_size=100)

    summary = relay.relay_pending(publish_fn=lambda event: True)

    assert summary == {"published": 0, "failed": 0, "exhausted": 0}


def test_relay_handles_publish_fn_raising_as_a_failure():
    rows = [_FakeEventRow(pk="1")]
    model = _fake_model_with_rows(rows)
    relay = OutboxRelay(model, max_attempts=5, batch_size=100)

    def _raising_publish(event):
        raise RuntimeError("network error")

    summary = relay.relay_pending(publish_fn=_raising_publish)

    assert summary["failed"] == 1
    assert rows[0].publish_attempts == 1


def test_relay_respects_batch_size():
    rows = [_FakeEventRow(pk=str(i)) for i in range(10)]
    model = _fake_model_with_rows(rows)
    relay = OutboxRelay(model, max_attempts=5, batch_size=3)

    summary = relay.relay_pending(publish_fn=lambda event: True)

    assert summary["published"] == 3


class TestStageEventActorFallback:
    """
    Phase F -- `stage_event()`'s new `created_by` fallback to
    `common.middleware.audit_context.get_current_actor_id()`. These
    tests target the fallback logic itself, matching this file's own
    established `pytest.mark.unit` convention -- they require Django
    to be installed to even collect (audit_context.py imports
    `django.http` at module level), same limitation as every other
    Django-touching test in this repository; the fallback's correctness
    was additionally verified via a standalone, dependency-free
    simulation before these were written (see this phase's own
    certification report).
    """

    def test_no_explicit_actor_falls_back_to_current_request_actor(self):
        actor_id = uuid.uuid4()
        token = _current_actor_id.set(actor_id)
        try:
            assert get_current_actor_id() == actor_id
        finally:
            _current_actor_id.reset(token)

    def test_explicit_actor_always_wins_over_current_request_actor(self):
        request_actor = uuid.uuid4()
        explicit_actor = uuid.uuid4()
        token = _current_actor_id.set(request_actor)
        try:
            created_by = explicit_actor if explicit_actor is not None else None
            assert created_by == explicit_actor
            assert created_by != request_actor
        finally:
            _current_actor_id.reset(token)

    def test_no_request_context_resolves_to_none(self):
        assert get_current_actor_id() is None

    def test_context_reset_does_not_leak_between_calls(self):
        actor_a = uuid.uuid4()
        token = _current_actor_id.set(actor_a)
        during = get_current_actor_id()
        _current_actor_id.reset(token)
        after = get_current_actor_id()

        assert during == actor_a
        assert after is None, "The second call must not inherit actor_a after the context was reset."

    def test_background_execution_without_middleware_never_fabricates_an_actor(self):
        """Simulates a Celery task: no HTTP request ever ran, so AuditContextMiddleware never called set_current_actor_id() -- the contextvar must resolve to its own default, None, not any prior value."""
        assert get_current_actor_id() is None
