"""
Test factories for Chat domain objects -- keeps every test file's
Arrange step short and consistent. Every factory accepts overrides
via **kwargs so individual tests can vary just the field under test.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from apps.chat.domain.aggregates import Conversation, Message
from apps.chat.domain.enums import ConversationType, MessageType, ParticipantRole
from apps.chat.domain.value_objects import MessageContent


def make_conversation(**overrides) -> Conversation:
    conversation_id = overrides.pop("id", uuid.uuid4())
    conversation_type = overrides.pop("conversation_type", ConversationType.CUSTOMER_SUPPORT)
    opened_by = overrides.pop("opened_by", uuid.uuid4())
    opener_role = overrides.pop("opener_role", ParticipantRole.CUSTOMER)
    at = overrides.pop("at", datetime.utcnow())
    conversation, _ = Conversation.open(conversation_id, conversation_type, opened_by, opener_role, at)
    for key, value in overrides.items():
        setattr(conversation, key, value)
    return conversation


def make_conversation_with_operator(**overrides) -> tuple[Conversation, uuid.UUID]:
    """A conversation with both a customer (the opener) and an assigned operator -- avoids every test that needs a two-participant conversation re-deriving the same setup."""
    operator_id = uuid.uuid4()
    conversation = make_conversation(**overrides)
    conversation.add_participant(operator_id, ParticipantRole.OPERATOR, datetime.utcnow())
    conversation.assign_operator(operator_id)
    return conversation, operator_id


def make_message(**overrides) -> Message:
    defaults = dict(
        message_id=uuid.uuid4(), conversation_id=uuid.uuid4(), sender_id=uuid.uuid4(), message_type=MessageType.TEXT,
        at=datetime.utcnow(), content=MessageContent("Hello, how can I help?"),
    )
    defaults.update(overrides)
    message, _ = Message.send(**defaults)
    return message
