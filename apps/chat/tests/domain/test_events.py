from __future__ import annotations

import ast
import dataclasses
import uuid

import pytest

import apps.chat.domain.events as events_module
import apps.chat.domain.exceptions as exceptions_module
from apps.chat.domain.events import (
    ConversationArchivedEvent, ConversationAssigned, ConversationClosedEvent, ConversationOpened,
    ConversationReopened, MessageDeleted, MessageDelivered, MessageEdited, MessageRead, MessageSent,
    ParticipantAdded, ParticipantRemoved,
)

pytestmark = pytest.mark.unit


def test_conversation_opened_payload():
    conversation_id, opened_by = uuid.uuid4(), uuid.uuid4()
    payload = ConversationOpened(conversation_id=conversation_id, conversation_type="customer_support", opened_by=opened_by).to_payload()
    assert payload["conversation_id"] == str(conversation_id)
    assert payload["conversation_type"] == "customer_support"


def test_participant_added_payload():
    payload = ParticipantAdded(conversation_id=uuid.uuid4(), participant_id=uuid.uuid4(), user_id=uuid.uuid4(), role="operator").to_payload()
    assert payload["role"] == "operator"


def test_participant_removed_payload():
    conversation_id, participant_id = uuid.uuid4(), uuid.uuid4()
    assert ParticipantRemoved(conversation_id=conversation_id, participant_id=participant_id).to_payload() == {"conversation_id": str(conversation_id), "participant_id": str(participant_id)}


def test_conversation_assigned_payload():
    conversation_id, operator_id = uuid.uuid4(), uuid.uuid4()
    assert ConversationAssigned(conversation_id=conversation_id, operator_id=operator_id).to_payload() == {"conversation_id": str(conversation_id), "operator_id": str(operator_id)}


def test_conversation_closed_event_payload():
    conversation_id = uuid.uuid4()
    assert ConversationClosedEvent(conversation_id=conversation_id).to_payload() == {"conversation_id": str(conversation_id)}


def test_conversation_reopened_payload():
    conversation_id = uuid.uuid4()
    assert ConversationReopened(conversation_id=conversation_id).to_payload() == {"conversation_id": str(conversation_id)}


def test_conversation_archived_event_payload():
    conversation_id = uuid.uuid4()
    assert ConversationArchivedEvent(conversation_id=conversation_id).to_payload() == {"conversation_id": str(conversation_id)}


def test_message_sent_payload():
    payload = MessageSent(message_id=uuid.uuid4(), conversation_id=uuid.uuid4(), sender_id=uuid.uuid4(), message_type="text").to_payload()
    assert payload["message_type"] == "text"


def test_message_edited_payload():
    message_id, conversation_id = uuid.uuid4(), uuid.uuid4()
    assert MessageEdited(message_id=message_id, conversation_id=conversation_id).to_payload() == {"message_id": str(message_id), "conversation_id": str(conversation_id)}


def test_message_deleted_payload():
    message_id, conversation_id = uuid.uuid4(), uuid.uuid4()
    assert MessageDeleted(message_id=message_id, conversation_id=conversation_id).to_payload() == {"message_id": str(message_id), "conversation_id": str(conversation_id)}


def test_message_delivered_payload():
    message_id = uuid.uuid4()
    assert MessageDelivered(message_id=message_id).to_payload() == {"message_id": str(message_id)}


def test_message_read_payload():
    message_id = uuid.uuid4()
    assert MessageRead(message_id=message_id).to_payload() == {"message_id": str(message_id)}


def test_every_event_is_a_frozen_dataclass():
    event_classes = [obj for name, obj in vars(events_module).items() if isinstance(obj, type) and dataclasses.is_dataclass(obj)]
    for cls in event_classes:
        assert cls.__dataclass_params__.frozen is True, f"{cls.__name__} is not frozen"


def test_events_are_immutable():
    event = MessageRead(message_id=uuid.uuid4())
    with pytest.raises(Exception):
        event.message_id = uuid.uuid4()  # type: ignore[misc]


def test_programmatically_verify_exactly_12_events():
    tree = ast.parse(open(events_module.__file__).read())
    class_names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert len(class_names) == 12, f"Expected exactly 12 Chat domain events, found {len(class_names)}: {class_names}"


def test_zero_collisions_between_events_and_exceptions():
    event_names = set(n.name for n in ast.parse(open(events_module.__file__).read()).body if isinstance(n, ast.ClassDef))
    exception_names = set(n.name for n in ast.parse(open(exceptions_module.__file__).read()).body if isinstance(n, ast.ClassDef))
    collisions = event_names & exception_names
    assert not collisions, f"Naming collisions found between events and exceptions: {collisions}"
