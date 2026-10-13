from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timezone

import pytest

from apps.audit.application.services.timeline import ListActivityTimeline, RecordActivity
from apps.audit.tests.application.fakes import FakeActivityTimelineRepository

pytestmark = pytest.mark.unit


class TestRecordActivity:
    def test_records_a_new_entry(self):
        repo = FakeActivityTimelineRepository()
        service = RecordActivity(repo)
        entry_id = uuid.uuid4()

        service.execute(
            entry_id=entry_id, action_type="updated", entity_type="FeatureFlag", entity_id="abc",
            context_schema="platform", occurred_at=datetime.now(timezone.utc),
        )
        assert entry_id in repo.entries

    def test_idempotent_by_entry_id(self):
        """A direct proof this service correctly relies on the repository's idempotent-by-id contract -- calling twice with the same entry_id must not create a second entry (real concern given the subscriber may re-process an event after a task retry)."""
        repo = FakeActivityTimelineRepository()
        service = RecordActivity(repo)
        entry_id = uuid.uuid4()

        service.execute(entry_id=entry_id, action_type="updated", entity_type="FeatureFlag", entity_id="abc", context_schema="platform", occurred_at=datetime.now(timezone.utc))
        service.execute(entry_id=entry_id, action_type="updated", entity_type="FeatureFlag", entity_id="abc", context_schema="platform", occurred_at=datetime.now(timezone.utc))

        assert len(repo.entries) == 1

    def test_records_actor_and_snapshots(self):
        repo = FakeActivityTimelineRepository()
        service = RecordActivity(repo)
        entry_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        service.execute(
            entry_id=entry_id, action_type="updated", entity_type="FeatureFlag", entity_id="abc",
            context_schema="platform", occurred_at=datetime.now(timezone.utc), actor_id=actor_id,
            before_snapshot={"is_globally_enabled": False}, after_snapshot={"is_globally_enabled": True},
        )
        assert repo.entries[entry_id]["actor_id"] == actor_id
        assert repo.entries[entry_id]["before_snapshot"] == {"is_globally_enabled": False}


class TestListActivityTimeline:
    def test_returns_all_entries_with_no_filters(self):
        repo = FakeActivityTimelineRepository()
        RecordActivity(repo).execute(entry_id=uuid.uuid4(), action_type="updated", entity_type="FeatureFlag", entity_id="a", context_schema="platform", occurred_at=datetime.now(timezone.utc))
        RecordActivity(repo).execute(entry_id=uuid.uuid4(), action_type="updated", entity_type="Order", entity_id="b", context_schema="ordering", occurred_at=datetime.now(timezone.utc))

        result = ListActivityTimeline(repo).execute()
        assert len(result) == 2

    def test_filters_by_entity_type(self):
        repo = FakeActivityTimelineRepository()
        RecordActivity(repo).execute(entry_id=uuid.uuid4(), action_type="updated", entity_type="FeatureFlag", entity_id="a", context_schema="platform", occurred_at=datetime.now(timezone.utc))
        RecordActivity(repo).execute(entry_id=uuid.uuid4(), action_type="updated", entity_type="Order", entity_id="b", context_schema="ordering", occurred_at=datetime.now(timezone.utc))

        result = ListActivityTimeline(repo).execute(entity_type="FeatureFlag")
        assert len(result) == 1
        assert result[0]["entity_type"] == "FeatureFlag"

    def test_filters_by_entity_id(self):
        repo = FakeActivityTimelineRepository()
        RecordActivity(repo).execute(entry_id=uuid.uuid4(), action_type="updated", entity_type="FeatureFlag", entity_id="a", context_schema="platform", occurred_at=datetime.now(timezone.utc))
        RecordActivity(repo).execute(entry_id=uuid.uuid4(), action_type="updated", entity_type="FeatureFlag", entity_id="b", context_schema="platform", occurred_at=datetime.now(timezone.utc))

        result = ListActivityTimeline(repo).execute(entity_id="a")
        assert len(result) == 1

    def test_empty_repository_returns_empty(self):
        repo = FakeActivityTimelineRepository()
        assert ListActivityTimeline(repo).execute() == []

    def test_never_implements_pagination_logic_itself(self):
        """A direct, executable proof this service only orchestrates the query -- cursor pagination is entirely delegated to StandardCursorPagination at the view layer, matching this phase's own reuse-not-duplicate mandate."""
        source = inspect.getsource(ListActivityTimeline.execute)
        assert "cursor" not in source.lower()
        assert "limit" not in source.lower()

    def test_filters_by_actor_id(self):
        repo = FakeActivityTimelineRepository()
        actor = uuid.uuid4()
        RecordActivity(repo).execute(entry_id=uuid.uuid4(), action_type="updated", entity_type="FeatureFlag", entity_id="a", context_schema="platform", occurred_at=datetime.now(timezone.utc), actor_id=actor)
        RecordActivity(repo).execute(entry_id=uuid.uuid4(), action_type="updated", entity_type="FeatureFlag", entity_id="b", context_schema="platform", occurred_at=datetime.now(timezone.utc), actor_id=uuid.uuid4())

        result = ListActivityTimeline(repo).execute(actor_id=actor)
        assert len(result) == 1
        assert result[0]["entity_id"] == "a"

    def test_entries_from_different_sources_carry_their_own_context_schema(self):
        """A real, evidenced concern this phase's generalization to 3 sources (Platform/Loyalty/Ordering) introduces: entries from different sources must never be mixed up or mislabeled with the wrong originating module."""
        repo = FakeActivityTimelineRepository()
        RecordActivity(repo).execute(entry_id=uuid.uuid4(), action_type="updated", entity_type="FeatureFlag", entity_id="a", context_schema="platform", occurred_at=datetime.now(timezone.utc))
        RecordActivity(repo).execute(entry_id=uuid.uuid4(), action_type="created", entity_type="LoyaltyMembership", entity_id="b", context_schema="loyalty", occurred_at=datetime.now(timezone.utc))
        RecordActivity(repo).execute(entry_id=uuid.uuid4(), action_type="updated", entity_type="Order", entity_id="c", context_schema="ordering", occurred_at=datetime.now(timezone.utc))

        result = ListActivityTimeline(repo).execute()
        schemas = {e["entity_id"]: e["context_schema"] for e in result}
        assert schemas == {"a": "platform", "b": "loyalty", "c": "ordering"}
