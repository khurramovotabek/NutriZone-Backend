"""
Notifications API serializers.

Every field name traced directly to the certified Domain/Infrastructure
contract, re-verified fresh this phase. **`title` is deliberately
required (`required=True` is DRF's own default -- no `allow_null`/
`required=False` is set), matching this phase's own explicit warning
and the certified Domain contract exactly: `Notification.title:
NotificationTitle` has no `| None`.** This is a direct contrast with
Reviews' own optional `title` field -- the two modules are not
analogous here, and copying that shape without checking would have
been the exact mistake this phase's own brief specifically warns
against.

**Command serializers exist and validate structurally even though
every one of their backing endpoints returns an honest HTTP 501**,
matching the identical precedent already established by Reviews'/
Chat's own Phase 3.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.notifications.domain.enums import NotificationChannel, NotificationPriority, NotificationType
from apps.notifications.domain.value_objects import MAX_BODY_LENGTH, MAX_TITLE_LENGTH

# --- Read shapes -----------------------------------------------------


class NotificationDeliverySerializer(serializers.Serializer):
    """Nested, subordinate to Notification -- never exposed as an independent top-level resource, per this phase's own explicit rule. `provider_reference` is intentionally excluded -- an opaque, internal-only Infrastructure detail, not something a client needs."""

    id = serializers.CharField(read_only=True)
    channel = serializers.ChoiceField(choices=NotificationChannel.values(), read_only=True)
    status = serializers.CharField(read_only=True)
    attempted_at = serializers.DateTimeField(read_only=True)
    delivered_at = serializers.DateTimeField(read_only=True, allow_null=True)
    failed_at = serializers.DateTimeField(read_only=True, allow_null=True)


class NotificationSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    notification_type = serializers.ChoiceField(choices=NotificationType.values(), read_only=True)
    priority = serializers.ChoiceField(choices=NotificationPriority.values(), read_only=True)
    title = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class NotificationDetailSerializer(NotificationSerializer):
    """Adds the full body, timestamps, and nested deliveries -- used by the single-notification detail endpoint, not the list endpoint (which stays lightweight, matching every prior module's card-vs-detail split)."""

    body = serializers.CharField(read_only=True)
    seen_at = serializers.DateTimeField(read_only=True, allow_null=True)
    read_at = serializers.DateTimeField(read_only=True, allow_null=True)
    deliveries = NotificationDeliverySerializer(many=True, read_only=True)


class NotificationStatisticsSerializer(serializers.Serializer):
    counts_by_status = serializers.DictField(read_only=True)


class NotificationPreferenceEntrySerializer(serializers.Serializer):
    """A single (channel, notification_type, enabled) tuple -- the domain-oriented representation this phase's own instructions require, rather than exposing `disabled_combinations`' internal sparse-JSON persistence shape directly."""

    channel = serializers.ChoiceField(choices=NotificationChannel.values())
    notification_type = serializers.ChoiceField(choices=NotificationType.values())
    enabled = serializers.BooleanField()


class NotificationPreferenceSerializer(serializers.Serializer):
    """Full matrix representation -- every (channel, notification_type) combination with its resolved enabled/disabled state, computed from `NotificationPreference.is_enabled()` for each pair, never the raw internal `disabled_combinations` list."""

    user_id = serializers.CharField(read_only=True)
    entries = NotificationPreferenceEntrySerializer(many=True, read_only=True)


# --- Command / request DTOs (every one backs an honest-501 endpoint) ---


class CreateNotificationSerializer(serializers.Serializer):
    recipient_id = serializers.UUIDField()
    notification_type = serializers.ChoiceField(choices=NotificationType.values())
    priority = serializers.ChoiceField(choices=NotificationPriority.values(), default=NotificationPriority.NORMAL.value)
    title = serializers.CharField(max_length=MAX_TITLE_LENGTH, allow_blank=False)
    body = serializers.CharField(max_length=MAX_BODY_LENGTH, allow_blank=False)
    template_key = serializers.CharField(required=False, allow_null=True, allow_blank=False)


class MarkSeenSerializer(serializers.Serializer):
    """No fields -- a pure state-transition command, matching the identical zero-field command serializer pattern already established by Wallet's/Loyalty's/Reviews'/Chat's own equivalents."""


class MarkReadSerializer(serializers.Serializer):
    """No fields -- matches `MarkSeenSerializer`'s rationale."""


class CancelNotificationSerializer(serializers.Serializer):
    """No fields -- matches `MarkSeenSerializer`'s rationale."""


class PreferenceChannelTypeSerializer(serializers.Serializer):
    """Backs both the disable and enable mutation endpoints -- identical payload shape for both commands."""

    channel = serializers.ChoiceField(choices=NotificationChannel.values())
    notification_type = serializers.ChoiceField(choices=NotificationType.values())
