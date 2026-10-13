"""
Chat API serializers.

Every field name traced directly to the certified Domain/Infrastructure
contract, re-verified fresh this phase (`Conversation.assigned_operator_id`,
never `customer_id`/`operator_id`; `Message.conversation_id`/`sender_id`
as plain strings). No ORM model or Domain entity is ever exposed
directly.

**Command serializers exist and validate structurally even though
every one of their backing endpoints returns an honest HTTP 501** --
matching the exact precedent already established by Reviews' own
Phase 3: the serializer validates shape before the view explains why
the operation can't complete yet.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.chat.domain.enums import AttachmentType, ConversationType, MessageType, ParticipantRole
from apps.chat.domain.value_objects import MAX_CONTENT_LENGTH

# --- Read shapes -----------------------------------------------------


class ParticipantSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    user_id = serializers.CharField(read_only=True)
    role = serializers.ChoiceField(choices=ParticipantRole.values(), read_only=True)
    joined_at = serializers.DateTimeField(read_only=True)
    removed_at = serializers.DateTimeField(read_only=True, allow_null=True)


class ConversationSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    conversation_type = serializers.ChoiceField(choices=ConversationType.values(), read_only=True)
    status = serializers.CharField(read_only=True)
    assigned_operator_id = serializers.CharField(read_only=True, allow_null=True)
    last_activity_at = serializers.DateTimeField(read_only=True, allow_null=True)


class ConversationDetailSerializer(ConversationSerializer):
    """Adds the full participant list -- used by the single-conversation detail endpoint, not the list endpoint (which stays lightweight, matching every prior module's card-vs-detail split)."""

    participants = ParticipantSerializer(many=True, read_only=True)


class MessageSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    conversation_id = serializers.CharField(read_only=True)
    sender_id = serializers.CharField(read_only=True)
    message_type = serializers.ChoiceField(choices=MessageType.values(), read_only=True)
    content = serializers.CharField(read_only=True, allow_null=True)
    status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class ChatStatisticsSerializer(serializers.Serializer):
    conversation_counts_by_status = serializers.DictField(read_only=True)


# --- Command / request DTOs (every one backs an honest-501 endpoint) ---


class OpenConversationSerializer(serializers.Serializer):
    conversation_type = serializers.ChoiceField(choices=ConversationType.values())
    opener_role = serializers.ChoiceField(choices=ParticipantRole.values())


class AddParticipantSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    role = serializers.ChoiceField(choices=ParticipantRole.values())


class AssignOperatorSerializer(serializers.Serializer):
    operator_user_id = serializers.UUIDField()


# What a participant may send over the API: SYSTEM messages are written by the platform itself (auto-replies), never a client.
CLIENT_MESSAGE_TYPES = [t for t in MessageType.values() if t != MessageType.SYSTEM.value]


class SendMessageSerializer(serializers.Serializer):
    message_type = serializers.ChoiceField(choices=CLIENT_MESSAGE_TYPES)
    content = serializers.CharField(max_length=MAX_CONTENT_LENGTH, required=False, allow_null=True, allow_blank=False)
    attachment_type = serializers.ChoiceField(choices=AttachmentType.values(), required=False, allow_null=True)
    attachment_url = serializers.URLField(required=False, allow_null=True)
    attachment_filename = serializers.CharField(required=False, allow_null=True, allow_blank=False)
    attachment_size_bytes = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    reply_to_message_id = serializers.UUIDField(required=False, allow_null=True)


class EditMessageSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=MAX_CONTENT_LENGTH, allow_blank=False)


# --- WebSocket protocol payload shapes -------------------------------


class WebSocketCommandSerializer(serializers.Serializer):
    """Envelope for every inbound client command -- `type` dispatches to a handler, `payload` is validated separately by that handler's own command-specific serializer above."""

    type = serializers.CharField()
    payload = serializers.DictField(required=False, default=dict)


class WebSocketErrorSerializer(serializers.Serializer):
    """Deterministic, stable error shape -- never a raw Python exception. `category` distinguishes invalid_request/unauthorized/not_found/unsupported_operation/internal_error, per this phase's own explicit "do not collapse all of these into one generic error" instruction."""

    type = serializers.CharField(default="error")
    category = serializers.ChoiceField(choices=["invalid_request", "unauthorized", "not_found", "unsupported_operation", "internal_error"])
    code = serializers.CharField()
    detail = serializers.CharField()
