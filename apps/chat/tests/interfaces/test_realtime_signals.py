"""
Realtime chat signals over the conversation socket -- heartbeat, typing
indicator, read receipts (persisted), presence -- plus sticker messages.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from apps.chat.domain.enums import MessageType
from apps.chat.domain.exceptions import UnknownSticker
from apps.chat.domain.value_objects import STICKER_CODES, MessageContent
from apps.chat.infrastructure import models as orm
from apps.chat.infrastructure.repositories import DjangoConversationRepository, DjangoMessageRepository
from apps.chat.interfaces.consumers import ChatConsumer
from apps.chat.tests.factories import make_conversation_with_operator, make_message

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.asyncio, pytest.mark.integration]


async def _connect(conversation_id, user_id) -> WebsocketCommunicator:
    communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), f"/ws/chat/{conversation_id}/")
    communicator.scope["user"] = SimpleNamespace(id=user_id, is_authenticated=True)
    communicator.scope["url_route"] = {"kwargs": {"conversation_id": str(conversation_id)}}
    connected, _ = await communicator.connect()
    assert connected
    return communicator


async def _next_of_type(communicator, wanted: str, timeout: float = 2):
    """Skips unrelated frames (e.g. the presence snapshot sent on connect) until one of `wanted` type arrives."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        frame = await communicator.receive_json_from(timeout=max(0.05, deadline - loop.time()))
        if frame.get("type") == wanted:
            return frame


async def _assert_never_receives(communicator, unwanted: str, window: float = 0.3) -> None:
    """Drains whatever else arrives; fails only if a frame of type `unwanted` shows up. Uses receive_nothing(), which -- unlike a timed-out receive -- doesn't cancel the app under test."""
    while not await communicator.receive_nothing(timeout=window):
        frame = await communicator.receive_json_from()
        assert frame.get("type") != unwanted, frame


async def _conversation():
    conversation, operator_id = make_conversation_with_operator()
    await database_sync_to_async(DjangoConversationRepository().save)(conversation)
    customer_id = next(p.user_id for p in conversation.participants.values() if p.user_id != operator_id)
    return conversation, customer_id, operator_id


async def test_ping_is_answered_with_pong():
    conversation, customer_id, _ = await _conversation()
    ws = await _connect(conversation.id, customer_id)
    await ws.send_json_to({"type": "ping"})
    assert (await _next_of_type(ws, "pong"))["type"] == "pong"
    await ws.disconnect()


async def test_typing_reaches_the_other_participant_but_not_the_sender():
    conversation, customer_id, operator_id = await _conversation()
    customer = await _connect(conversation.id, customer_id)
    operator = await _connect(conversation.id, operator_id)

    await customer.send_json_to({"type": "typing", "is_typing": True})

    frame = await _next_of_type(operator, "typing")
    assert frame == {"type": "typing", "user_id": str(customer_id), "is_typing": True}
    await _assert_never_receives(customer, "typing")
    await customer.disconnect()
    await operator.disconnect()


async def test_presence_is_broadcast_when_the_other_side_joins():
    conversation, customer_id, operator_id = await _conversation()
    customer = await _connect(conversation.id, customer_id)
    operator = await _connect(conversation.id, operator_id)

    # the first presence frame is the snapshot taken on connect (operator still offline); then the live "joined" signal
    snapshot = await _next_of_type(customer, "presence")
    assert snapshot == {"type": "presence", "user_id": str(operator_id), "online": False}
    joined = await _next_of_type(customer, "presence")
    assert joined == {"type": "presence", "user_id": str(operator_id), "online": True}
    await operator.disconnect()
    await customer.disconnect()


async def test_read_marks_the_other_sides_messages_and_notifies_the_sender():
    # Out of working hours (evenings, Sundays) a customer's message also gets the SYSTEM auto-reply, which the
    # operator would then read too -- switched off so this test counts only the two messages it sends, at any hour.
    from apps.chat.infrastructure.models import ChatSettings

    await database_sync_to_async(lambda: ChatSettings.objects.filter(pk=ChatSettings.load().pk).update(auto_reply_enabled=False))()
    conversation, customer_id, operator_id = await _conversation()
    repo = DjangoMessageRepository()
    from_customer = make_message(conversation_id=conversation.id, sender_id=customer_id)
    from_operator = make_message(conversation_id=conversation.id, sender_id=operator_id)
    await database_sync_to_async(repo.save)(from_customer)
    await database_sync_to_async(repo.save)(from_operator)

    customer = await _connect(conversation.id, customer_id)
    operator = await _connect(conversation.id, operator_id)
    await operator.send_json_to({"type": "read"})

    frame = await _next_of_type(customer, "messages.read")
    assert frame["reader_id"] == str(operator_id)

    rows = await database_sync_to_async(lambda: {r.id: r.read_at for r in orm.MessageModel.objects.filter(conversation_id=conversation.id)})()
    assert rows[from_customer.id] is not None  # the operator read the customer's message
    assert rows[from_operator.id] is None  # one's own message is never "read" by oneself
    events = await database_sync_to_async(lambda: orm.ChatOutboxEvent.objects.filter(event_type="MessageRead").count())()
    assert events == 1

    # a second "read" with nothing new is a silent no-op
    await operator.send_json_to({"type": "read"})
    await _assert_never_receives(customer, "messages.read")
    await customer.disconnect()
    await operator.disconnect()


class TestStickers:
    @pytest.mark.parametrize("code", sorted(STICKER_CODES))
    async def test_every_published_sticker_can_be_sent(self, code):
        message = make_message(message_type=MessageType.STICKER, content=MessageContent(code))
        assert message.message_type == MessageType.STICKER

    async def test_unknown_or_missing_sticker_code_is_rejected(self):
        with pytest.raises(UnknownSticker):
            make_message(message_type=MessageType.STICKER, content=MessageContent("<script>"))
        with pytest.raises(UnknownSticker):
            make_message(message_type=MessageType.STICKER, content=None, at=datetime.utcnow())
