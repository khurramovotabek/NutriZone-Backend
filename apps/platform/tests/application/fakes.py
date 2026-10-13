"""
In-memory fakes implementing application/ports.py's Protocols, used
across Application-layer tests -- per Django Implementation Blueprint
§11's rule that application-layer unit tests fake their repository/
gateway ports rather than hitting a real database.
"""
from __future__ import annotations

import uuid

from apps.platform.domain.aggregates import FeatureFlag


def collect_events(events: list):
    def _stage(new_events):
        events.extend(new_events)
    return _stage


class FakeFeatureFlagRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, FeatureFlag] = {}

    def get_by_id(self, flag_id):
        return self.by_id.get(flag_id)

    def get_by_key(self, key: str):
        return next((f for f in self.by_id.values() if f.key == key), None)

    def list_all(self):
        return list(self.by_id.values())

    def save(self, flag: FeatureFlag) -> FeatureFlag:
        self.by_id[flag.id] = flag
        return flag


class FakeFlagPublisher:
    def __init__(self) -> None:
        self.published: list[FeatureFlag] = []

    def publish(self, flag: FeatureFlag) -> None:
        self.published.append(flag)
