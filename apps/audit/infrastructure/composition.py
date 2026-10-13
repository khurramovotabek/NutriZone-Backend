"""
Composition root for the `audit` module.
"""
from __future__ import annotations

from apps.audit.application.services.timeline import ListActivityTimeline, RecordActivity
from apps.audit.infrastructure.repositories import DjangoActivityTimelineRepository


def build_activity_timeline_repository() -> DjangoActivityTimelineRepository:
    return DjangoActivityTimelineRepository()


def build_list_activity_timeline() -> ListActivityTimeline:
    return ListActivityTimeline(build_activity_timeline_repository())


def build_record_activity() -> RecordActivity:
    return RecordActivity(build_activity_timeline_repository())
