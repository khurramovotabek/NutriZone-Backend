"""
Real, live-verified regression tests for the Telegram bot's "Chat"
integration -- previously disclosed as scope-limited to acknowledging
a typed message with no real wiring into apps.chat's own Conversation/
Message aggregates. This phase closes that gap: the "Chat" menu
button opens (or resumes) a real Conversation, and subsequent plain-
text messages are written as real Messages via the same SendMessage
Application Service the REST API itself uses.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from django.test import Client

from apps.identity.infrastructure import models as identity_orm

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_rate_limit_state():
    from core.caching.redis_client import get_redis_client

    get_redis_client().flushall()
    yield


def _real_user(telegram_user_id: int):
    return identity_orm.User.objects.create(
        id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active",
        telegram_user_id=telegram_user_id, full_name="Test Customer",
    )


class TestChatButtonOpensRealConversation:
    def test_chat_button_opens_a_real_conversation(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_BOT_USERNAME = "nutrizone_test_bot"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        user = _real_user(tg_user_id)

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}

        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send:
            chat_callback = {"update_id": 1, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "menu:chat"}}
            response = client.post("/api/v1/telegram/webhook", data=json.dumps(chat_callback), content_type="application/json", **webhook_auth)
            assert response.status_code == 200
            assert mock_send.called

        from apps.chat.infrastructure.models import ConversationModel, ParticipantModel

        conversation = ConversationModel.objects.filter(conversation_type="customer_support").order_by("-created_at").first()
        assert conversation is not None
        assert conversation.status == "open"
        assert ParticipantModel.objects.filter(conversation_id=conversation.id, user_id=user.id).exists()

    def test_pressing_chat_multiple_times_reuses_the_same_conversation(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_BOT_USERNAME = "nutrizone_test_bot"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        _real_user(tg_user_id)

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}

        from apps.chat.infrastructure.models import ConversationModel

        count_before = ConversationModel.objects.filter(conversation_type="customer_support").count()

        with patch("apps.telegram_bot.interfaces.callback_router._send"):
            chat_callback = {"update_id": 1, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "menu:chat"}}
            client.post("/api/v1/telegram/webhook", data=json.dumps(chat_callback), content_type="application/json", **webhook_auth)
            client.post("/api/v1/telegram/webhook", data=json.dumps(chat_callback), content_type="application/json", **webhook_auth)

        assert ConversationModel.objects.filter(conversation_type="customer_support").count() - count_before == 1

    def test_unregistered_user_pressing_chat_is_asked_to_register(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_BOT_USERNAME = "nutrizone_test_bot"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}

        from apps.chat.infrastructure.models import ConversationModel

        count_before = ConversationModel.objects.count()

        with patch("apps.telegram_bot.interfaces.callback_router._send"):
            chat_callback = {"update_id": 1, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "menu:chat"}}
            response = client.post("/api/v1/telegram/webhook", data=json.dumps(chat_callback), content_type="application/json", **webhook_auth)
            assert response.status_code == 200

        assert ConversationModel.objects.count() == count_before


class TestTypedMessageIsWrittenAsRealChatMessage:
    def test_typed_message_after_chat_button_is_a_real_message(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_BOT_USERNAME = "nutrizone_test_bot"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        user = _real_user(tg_user_id)

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}

        with patch("apps.telegram_bot.interfaces.callback_router._send"):
            chat_callback = {"update_id": 1, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "menu:chat"}}
            client.post("/api/v1/telegram/webhook", data=json.dumps(chat_callback), content_type="application/json", **webhook_auth)

        from apps.chat.infrastructure.models import ConversationModel

        conversation = ConversationModel.objects.filter(conversation_type="customer_support").order_by("-created_at").first()

        with patch("apps.telegram_bot.interfaces.api.v1.views._reply_text") as mock_reply:
            text_message = {"update_id": 2, "message": {"message_id": 2, "chat": {"id": tg_user_id, "type": "private"}, "from": {"id": tg_user_id}, "text": "Salom, buyurtmam qachon yetadi?"}}
            response = client.post("/api/v1/telegram/webhook", data=json.dumps(text_message), content_type="application/json", **webhook_auth)
            assert response.status_code == 200
            assert mock_reply.called

        from apps.chat.infrastructure.models import MessageModel

        message = MessageModel.objects.filter(conversation_id=conversation.id).order_by("-created_at").first()
        assert message is not None
        assert message.content == "Salom, buyurtmam qachon yetadi?"
        assert message.sender_id == user.id

    def test_typed_message_without_active_chat_is_not_written_anywhere(self, settings):
        """A user who has not pressed the "Chat" button must not have their ordinary messages silently turned into support conversation messages."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_BOT_USERNAME = "nutrizone_test_bot"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        _real_user(tg_user_id)

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}

        from apps.chat.infrastructure.models import MessageModel

        count_before = MessageModel.objects.count()

        text_message = {"update_id": 1, "message": {"message_id": 1, "chat": {"id": tg_user_id, "type": "private"}, "from": {"id": tg_user_id}, "text": "Random unrelated text"}}
        response = client.post("/api/v1/telegram/webhook", data=json.dumps(text_message), content_type="application/json", **webhook_auth)
        assert response.status_code == 200

        assert MessageModel.objects.count() == count_before


class TestEndChatButton:
    def test_end_chat_exits_active_mode_without_closing_the_conversation(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_BOT_USERNAME = "nutrizone_test_bot"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"

        tg_user_id = uuid.uuid4().int % 900000000
        _real_user(tg_user_id)

        client = Client()
        webhook_auth = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}

        with patch("apps.telegram_bot.interfaces.callback_router._send"):
            chat_callback = {"update_id": 1, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "menu:chat"}}
            client.post("/api/v1/telegram/webhook", data=json.dumps(chat_callback), content_type="application/json", **webhook_auth)

        from apps.chat.infrastructure.models import ConversationModel

        conversation = ConversationModel.objects.filter(conversation_type="customer_support").order_by("-created_at").first()

        with patch("apps.telegram_bot.interfaces.callback_router.send_main_menu") as mock_menu:
            end_callback = {"update_id": 2, "callback_query": {"id": "cbq2", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}}, "data": "menu:endchat"}}
            response = client.post("/api/v1/telegram/webhook", data=json.dumps(end_callback), content_type="application/json", **webhook_auth)
            assert response.status_code == 200
            assert mock_menu.called

        conversation.refresh_from_db()
        assert conversation.status == "open"

        from apps.telegram_bot.interfaces import chat_state

        assert chat_state.get_active_conversation(tg_user_id) is None
