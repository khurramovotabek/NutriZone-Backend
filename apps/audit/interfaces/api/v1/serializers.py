"""Audit API serializers. Public projection only -- exposes exactly the columns Database Blueprint §4.19 defines, nothing internal."""
from __future__ import annotations

from rest_framework import serializers


class ActivityTimelineEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    actor_id = serializers.UUIDField(read_only=True, allow_null=True)
    action_type = serializers.CharField(read_only=True)
    entity_type = serializers.CharField(read_only=True)
    entity_id = serializers.CharField(read_only=True)
    context_schema = serializers.CharField(read_only=True)
    before_snapshot = serializers.DictField(read_only=True, allow_null=True)
    after_snapshot = serializers.DictField(read_only=True, allow_null=True)
    occurred_at = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
