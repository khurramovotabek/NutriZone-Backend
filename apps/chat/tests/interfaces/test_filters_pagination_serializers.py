from __future__ import annotations

import re
import uuid

import pytest
from django.http import QueryDict

from apps.chat.interfaces.api.v1.filters import parse_conversation_list_params, parse_pagination_only
from apps.chat.interfaces.api.v1.pagination import ChatPagination
from apps.chat.interfaces.api.v1.serializers import (
    AddParticipantSerializer, AssignOperatorSerializer, EditMessageSerializer, OpenConversationSerializer,
    SendMessageSerializer, WebSocketCommandSerializer, WebSocketErrorSerializer,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def _qd(params: dict) -> QueryDict:
    qd = QueryDict(mutable=True)
    for key, value in params.items():
        qd[key] = value
    return qd


class TestConversationListParams:
    def test_defaults(self):
        params = parse_conversation_list_params(_qd({}))
        assert params.page == 1
        assert params.status is None

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationFailed):
            parse_conversation_list_params(_qd({"filter[status]": "bogus"}))

    def test_valid_status_accepted(self):
        params = parse_conversation_list_params(_qd({"filter[status]": "open"}))
        assert params.status == "open"


class TestPaginationOnly:
    def test_returns_page_and_page_size(self):
        page, page_size = parse_pagination_only(_qd({}))
        assert page == 1
        assert page_size == 20


class TestPagination:
    def test_defaults(self):
        pagination = ChatPagination.from_query_params(_qd({}))
        assert pagination.page_size == 20

    def test_caps_at_100(self):
        pagination = ChatPagination.from_query_params(_qd({"page_size": "9999"}))
        assert pagination.page_size == 100

    def test_invalid_page_raises(self):
        with pytest.raises(ValidationFailed):
            ChatPagination.from_query_params(_qd({"page": "not-a-number"}))


class TestSerializers:
    def test_open_conversation_serializer_valid(self):
        serializer = OpenConversationSerializer(data={"conversation_type": "customer_support", "opener_role": "customer"})
        assert serializer.is_valid()

    def test_add_participant_serializer_requires_valid_role(self):
        serializer = AddParticipantSerializer(data={"user_id": str(uuid.uuid4()), "role": "not_a_real_role"})
        assert not serializer.is_valid()

    def test_assign_operator_serializer_requires_uuid(self):
        serializer = AssignOperatorSerializer(data={"operator_user_id": "not-a-uuid"})
        assert not serializer.is_valid()

    def test_send_message_serializer_valid_text(self):
        serializer = SendMessageSerializer(data={"message_type": "text", "content": "Hello"})
        assert serializer.is_valid()

    def test_send_message_serializer_valid_attachment_only(self):
        serializer = SendMessageSerializer(data={"message_type": "attachment", "attachment_type": "image", "attachment_url": "https://example.com/a.jpg", "attachment_filename": "a.jpg", "attachment_size_bytes": 1024})
        assert serializer.is_valid()

    def test_edit_message_serializer_rejects_empty_content(self):
        serializer = EditMessageSerializer(data={"content": ""})
        assert not serializer.is_valid()

    def test_websocket_command_serializer_defaults_empty_payload(self):
        serializer = WebSocketCommandSerializer(data={"type": "message.send"})
        assert serializer.is_valid()
        assert serializer.validated_data["payload"] == {}

    def test_websocket_error_serializer_requires_valid_category(self):
        serializer = WebSocketErrorSerializer(data={"category": "not_a_real_category", "code": "X", "detail": "y"})
        assert not serializer.is_valid()

    def test_websocket_error_serializer_valid(self):
        serializer = WebSocketErrorSerializer(data={"category": "unsupported_operation", "code": "X", "detail": "y"})
        assert serializer.is_valid()

    def test_zero_duplicate_serializer_names(self):
        names = re.findall(r"^class (\w+)", open("apps/chat/interfaces/api/v1/serializers.py").read(), re.M)
        assert len(names) == len(set(names))
