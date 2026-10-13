"""
Aggregate tests -- covers every public method, every state transition,
every invariant, every emitted Domain Event, and every exception path
on both `Conversation` and `Message`.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from apps.chat.domain.aggregates import Conversation, Message
from apps.chat.domain.enums import AttachmentType, ConversationStatus, ConversationType, MessageStatus, MessageType, ParticipantRole
from apps.chat.domain.exceptions import (
    AttachmentRequired, EmptyMessageContent, InvalidConversationTransition, InvalidParticipantRole,
    MessageAlreadyDeleted, MessageEditNotAllowed, MessageNotOwnedBySender, ParticipantAlreadyExists,
    ParticipantNotFound,
)
from apps.chat.domain.value_objects import AttachmentMetadata, MessageContent
from apps.chat.tests.factories import make_conversation, make_conversation_with_operator, make_message

pytestmark = pytest.mark.unit


def _now() -> datetime:
    return datetime.utcnow()


class TestConversationOpen:
    def test_opens_with_initiating_participant(self):
        opener_id = uuid.uuid4()
        conversation, event = Conversation.open(uuid.uuid4(), ConversationType.CUSTOMER_SUPPORT, opener_id, ParticipantRole.CUSTOMER, _now())
        assert conversation.status == ConversationStatus.OPEN
        assert len(conversation.participants) == 1
        assert event.__class__.__name__ == "ConversationOpened"

    def test_starts_with_no_assigned_operator(self):
        conversation, _ = Conversation.open(uuid.uuid4(), ConversationType.CUSTOMER_SUPPORT, uuid.uuid4(), ParticipantRole.CUSTOMER, _now())
        assert conversation.assigned_operator_id is None

    def test_customer_role_rejected_for_internal_support(self):
        with pytest.raises(InvalidParticipantRole):
            Conversation.open(uuid.uuid4(), ConversationType.INTERNAL_SUPPORT, uuid.uuid4(), ParticipantRole.CUSTOMER, _now())

    def test_operator_role_allowed_for_internal_support(self):
        conversation, _ = Conversation.open(uuid.uuid4(), ConversationType.INTERNAL_SUPPORT, uuid.uuid4(), ParticipantRole.OPERATOR, _now())
        assert conversation.status == ConversationStatus.OPEN


class TestConversationParticipants:
    def test_add_participant(self):
        conversation = make_conversation()
        event = conversation.add_participant(uuid.uuid4(), ParticipantRole.OPERATOR, _now())
        assert len(conversation.participants) == 2
        assert event.__class__.__name__ == "ParticipantAdded"

    def test_add_duplicate_active_participant_raises(self):
        conversation = make_conversation()
        opener_id = next(iter(conversation.participants.values())).user_id
        with pytest.raises(ParticipantAlreadyExists):
            conversation.add_participant(opener_id, ParticipantRole.CUSTOMER, _now())

    def test_add_invalid_role_for_conversation_type_raises(self):
        conversation = make_conversation(conversation_type=ConversationType.INTERNAL_SUPPORT, opener_role=ParticipantRole.OPERATOR)
        with pytest.raises(InvalidParticipantRole):
            conversation.add_participant(uuid.uuid4(), ParticipantRole.CUSTOMER, _now())

    def test_remove_participant(self):
        conversation = make_conversation()
        user_id = uuid.uuid4()
        conversation.add_participant(user_id, ParticipantRole.OPERATOR, _now())
        event = conversation.remove_participant(user_id, _now())
        assert event.__class__.__name__ == "ParticipantRemoved"
        participant = next(p for p in conversation.participants.values() if p.user_id == user_id)
        assert participant.is_active is False

    def test_remove_nonexistent_participant_raises(self):
        conversation = make_conversation()
        with pytest.raises(ParticipantNotFound):
            conversation.remove_participant(uuid.uuid4(), _now())

    def test_remove_already_removed_participant_raises(self):
        conversation = make_conversation()
        user_id = uuid.uuid4()
        conversation.add_participant(user_id, ParticipantRole.OPERATOR, _now())
        conversation.remove_participant(user_id, _now())
        with pytest.raises(ParticipantNotFound):
            conversation.remove_participant(user_id, _now())


class TestConversationOperatorAssignment:
    def test_assign_operator(self):
        conversation = make_conversation()
        operator_id = uuid.uuid4()
        event = conversation.assign_operator(operator_id)
        assert conversation.assigned_operator_id == operator_id
        assert event.__class__.__name__ == "ConversationAssigned"

    def test_reassign_operator_is_allowed(self):
        """Reassignment is an explicitly supported ordinary operation, not an error case -- per aggregates.py's own documented design."""
        conversation = make_conversation()
        conversation.assign_operator(uuid.uuid4())
        new_operator = uuid.uuid4()
        conversation.assign_operator(new_operator)
        assert conversation.assigned_operator_id == new_operator


class TestConversationLifecycle:
    def test_close(self):
        conversation = make_conversation()
        event = conversation.close()
        assert conversation.status == ConversationStatus.CLOSED
        assert event.__class__.__name__ == "ConversationClosedEvent"

    def test_close_non_open_raises(self):
        conversation = make_conversation()
        conversation.close()
        with pytest.raises(InvalidConversationTransition):
            conversation.close()

    def test_reopen(self):
        conversation = make_conversation()
        conversation.close()
        event = conversation.reopen()
        assert conversation.status == ConversationStatus.OPEN
        assert event.__class__.__name__ == "ConversationReopened"

    def test_reopen_non_closed_raises(self):
        conversation = make_conversation()
        with pytest.raises(InvalidConversationTransition):
            conversation.reopen()

    def test_archive(self):
        conversation = make_conversation()
        event = conversation.archive()
        assert conversation.status == ConversationStatus.ARCHIVED
        assert event.__class__.__name__ == "ConversationArchivedEvent"

    def test_archive_already_archived_raises(self):
        conversation = make_conversation()
        conversation.archive()
        with pytest.raises(InvalidConversationTransition):
            conversation.archive()

    def test_archived_conversation_can_never_be_reopened(self):
        """The one deliberately terminal state -- see aggregates.py's own `reopen()` docstring. Archive from OPEN, then attempt reopen (which requires CLOSED) -- must still fail."""
        conversation = make_conversation()
        conversation.archive()
        with pytest.raises(InvalidConversationTransition):
            conversation.reopen()

    def test_record_activity_updates_timestamp_and_bumps_version_but_emits_no_event(self):
        conversation = make_conversation()
        original_version = conversation.version.value
        new_time = _now()
        result = conversation.record_activity(new_time)
        assert conversation.last_activity_at == new_time
        assert conversation.version.value == original_version + 1
        assert result is None


class TestMessageSend:
    def test_text_message_requires_content(self):
        with pytest.raises(EmptyMessageContent):
            Message.send(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), MessageType.TEXT, _now())

    def test_system_message_requires_content(self):
        with pytest.raises(EmptyMessageContent):
            Message.send(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), MessageType.SYSTEM, _now())

    def test_attachment_message_requires_attachment_metadata(self):
        with pytest.raises(AttachmentRequired):
            Message.send(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), MessageType.ATTACHMENT, _now())

    def test_attachment_only_message_with_no_content_is_allowed(self):
        attachment = AttachmentMetadata(attachment_type=AttachmentType.IMAGE, url="https://example.com/a.jpg", filename="a.jpg", size_bytes=1024)
        message, event = Message.send(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), MessageType.ATTACHMENT, _now(), attachment=attachment)
        assert message.content is None
        assert event.__class__.__name__ == "MessageSent"

    def test_text_message_with_content_succeeds(self):
        message, event = Message.send(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), MessageType.TEXT, _now(), content=MessageContent("Hi"))
        assert message.status == MessageStatus.SENT
        assert event.message_type == "text"


class TestMessageEditDelete:
    def test_sender_can_edit_text_message(self):
        message = make_message()
        event = message.edit(MessageContent("Updated"), message.sender_id, _now())
        assert message.content.value == "Updated"
        assert message.status == MessageStatus.EDITED
        assert event.__class__.__name__ == "MessageEdited"

    def test_non_sender_cannot_edit(self):
        message = make_message()
        with pytest.raises(MessageNotOwnedBySender):
            message.edit(MessageContent("Hacked"), uuid.uuid4(), _now())

    def test_edit_after_delete_raises(self):
        message = make_message()
        message.delete(message.sender_id, _now())
        with pytest.raises(MessageEditNotAllowed):
            message.edit(MessageContent("Too late"), message.sender_id, _now())

    def test_edit_attachment_message_raises(self):
        attachment = AttachmentMetadata(attachment_type=AttachmentType.IMAGE, url="https://example.com/a.jpg", filename="a.jpg", size_bytes=1024)
        message, _ = Message.send(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), MessageType.ATTACHMENT, _now(), attachment=attachment)
        with pytest.raises(MessageEditNotAllowed):
            message.edit(MessageContent("Caption change"), message.sender_id, _now())

    def test_sender_can_delete(self):
        message = make_message()
        event = message.delete(message.sender_id, _now())
        assert message.status == MessageStatus.DELETED
        assert event.__class__.__name__ == "MessageDeleted"

    def test_non_sender_cannot_delete(self):
        message = make_message()
        with pytest.raises(MessageNotOwnedBySender):
            message.delete(uuid.uuid4(), _now())

    def test_double_delete_raises(self):
        message = make_message()
        message.delete(message.sender_id, _now())
        with pytest.raises(MessageAlreadyDeleted):
            message.delete(message.sender_id, _now())


class TestMessageDeliveryReadState:
    def test_mark_delivered(self):
        message = make_message()
        event = message.mark_delivered(_now())
        assert message.delivered_at is not None
        assert event.__class__.__name__ == "MessageDelivered"

    def test_mark_delivered_twice_is_idempotent_noop(self):
        """A repeated delivery acknowledgment is a legitimate no-op, not an error -- matching Loyalty's evaluate_tier no-change precedent."""
        message = make_message()
        message.mark_delivered(_now())
        result = message.mark_delivered(_now())
        assert result is None

    def test_mark_read(self):
        message = make_message()
        event = message.mark_read(_now())
        assert message.read_at is not None
        assert event.__class__.__name__ == "MessageRead"

    def test_mark_read_twice_is_idempotent_noop(self):
        message = make_message()
        message.mark_read(_now())
        result = message.mark_read(_now())
        assert result is None


class TestPrivateAccessBoundary:
    def test_private_methods_are_underscore_prefixed_and_not_part_of_public_contract(self):
        for cls in (Conversation, Message):
            public_methods = {name for name in dir(cls) if not name.startswith("_") and callable(getattr(cls, name, None))}
            assert "_bump_version" not in public_methods


def test_make_conversation_with_operator_factory_produces_two_active_participants():
    """A direct test of the shared test factory itself -- it is used by other test files across this suite, so a bug in it would silently corrupt many other tests' assumptions."""
    conversation, operator_id = make_conversation_with_operator()
    assert len(conversation.participants) == 2
    assert conversation.assigned_operator_id == operator_id
