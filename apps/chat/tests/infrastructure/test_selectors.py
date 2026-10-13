from __future__ import annotations

import uuid

import pytest

from apps.chat.infrastructure.repositories import DjangoConversationRepository, DjangoMessageRepository
from apps.chat.infrastructure.selectors import ChatStatisticsSelector, ConversationSelector, MessageSelector
from apps.chat.tests.factories import make_conversation, make_message

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestConversationSelector:
    def test_list_for_user(self):
        conversation = make_conversation()
        opener_id = next(iter(conversation.participants.values())).user_id
        DjangoConversationRepository().save(conversation)
        results, total = ConversationSelector().list_for_user(opener_id, status=None, page=1, page_size=20)
        assert total == 1
        assert results[0]["id"] == str(conversation.id)

    def test_list_for_user_filters_by_status(self):
        conversation = make_conversation()
        opener_id = next(iter(conversation.participants.values())).user_id
        conversation.close()
        DjangoConversationRepository().save(conversation)
        results, total = ConversationSelector().list_for_user(opener_id, status="closed", page=1, page_size=20)
        assert total == 1
        results, total = ConversationSelector().list_for_user(opener_id, status="open", page=1, page_size=20)
        assert total == 0

    def test_get_detail(self):
        conversation = make_conversation()
        DjangoConversationRepository().save(conversation)
        card = ConversationSelector().get_detail(conversation.id)
        assert card is not None
        assert card["id"] == str(conversation.id)

    def test_get_detail_missing_returns_none(self):
        assert ConversationSelector().get_detail(uuid.uuid4()) is None


class TestMessageSelector:
    def test_list_for_conversation(self):
        message = make_message()
        DjangoMessageRepository().save(message)
        results, total = MessageSelector().list_for_conversation(message.conversation_id, page=1, page_size=20)
        assert total == 1
        assert results[0]["content"] == message.content.value


class TestChatStatisticsSelector:
    def test_conversation_counts_by_status(self):
        DjangoConversationRepository().save(make_conversation())
        counts = ChatStatisticsSelector().conversation_counts_by_status()
        assert counts.get("open", 0) >= 1
