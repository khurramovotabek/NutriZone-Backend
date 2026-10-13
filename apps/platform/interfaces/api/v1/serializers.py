"""
Platform API serializers.

Structural validation only, matching every prior module's convention
(MIC §6's "one place" rule -- `rollout_percentage`'s 0-100 range is
validated in the Domain, not duplicated here).
"""
from __future__ import annotations

from rest_framework import serializers


class FeatureFlagSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    key = serializers.CharField(read_only=True)
    is_globally_enabled = serializers.BooleanField(read_only=True)
    rollout_percentage = serializers.IntegerField(read_only=True, allow_null=True)
    rollout_scope = serializers.DictField(read_only=True)


class DefineFeatureFlagSerializer(serializers.Serializer):
    key = serializers.CharField(max_length=128)
    is_globally_enabled = serializers.BooleanField(required=False, default=False)
    rollout_percentage = serializers.IntegerField(required=False, allow_null=True, default=None, min_value=0, max_value=100)
    rollout_scope = serializers.DictField(required=False, default=dict)


class UpdateFeatureFlagSerializer(serializers.Serializer):
    """`PATCH /settings/feature-flags/{id}` -- every field optional. Deliberately no `allow_null=True`/`default=`: neither `is_globally_enabled` nor `rollout_scope` is ever meaningfully `None` in the Domain (both are non-nullable, always `bool`/`dict`) -- "not supplied" is represented by the key being absent from `validated_data` entirely (DRF's own `required=False`-without-`default` behavior), which the view reads via `.get(key)`, matching the proven pattern from the Identity module's own PATCH-semantics fix."""


class ContactMessageCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    subject = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    message = serializers.CharField(max_length=5000, min_length=5)

    is_globally_enabled = serializers.BooleanField(required=False)
    rollout_percentage = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=100)
    rollout_scope = serializers.DictField(required=False)


class EvaluatedFlagsSerializer(serializers.Serializer):
    """`GET /settings/feature-flags` response -- a flat `{key: bool}` map, matching REST API Blueprint §13.18's "evaluated flags for current context" exactly. No rollout internals exposed (Security §16)."""

    flags = serializers.DictField(child=serializers.BooleanField())
