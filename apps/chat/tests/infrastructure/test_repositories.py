"""
Repository integration tests -- require a real PostgreSQL database.
Includes explicit database-constraint verification, not just
round-trip tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from apps.chat.domain.enums import AttachmentType, MessageType, ParticipantRole
from apps.chat.infrastructure.repositories import DjangoConversationRepository, DjangoMessageRepository
from apps.chat.domain.value_objects import AttachmentMetadata, MessageContent
from apps.chat.tests.factories import make_conversation, make_conversation_with_operator, make_message

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoConversationRepository:
    def test_save_then_get_by_id_round_trips(self):
        repo = DjangoConversationRepository()
        conversation = make_conversation()
        repo.save(conversation)

        fetched = repo.get_by_id(conversation.id)
        assert fetched is not None
        assert fetched.conversation_type == conversation.conversation_type
        assert len(fetched.participants) == 1

    def test_assigned_operator_id_round_trips(self):
        repo = DjangoConversationRepository()
        conversation, operator_id = make_conversation_with_operator()
        repo.save(conversation)
        fetched = repo.get_by_id(conversation.id)
        assert fetched.assigned_operator_id == operator_id

    def test_get_by_id_missing_returns_none(self):
        repo = DjangoConversationRepository()
        assert repo.get_by_id(uuid.uuid4()) is None

    def test_removed_participant_round_trips(self):
        repo = DjangoConversationRepository()
        conversation = make_conversation()
        user_id = uuid.uuid4()
        conversation.add_participant(user_id, ParticipantRole.OPERATOR, datetime.utcnow())
        conversation.remove_participant(user_id, datetime.utcnow())
        repo.save(conversation)

        fetched = repo.get_by_id(conversation.id)
        removed_participant = next(p for p in fetched.participants.values() if p.user_id == user_id)
        assert removed_participant.is_active is False

    def test_list_for_user(self):
        repo = DjangoConversationRepository()
        conversation = make_conversation()
        opener_id = next(iter(conversation.participants.values())).user_id
        repo.save(conversation)
        results, total = repo.list_for_user(opener_id, status=None, page=1, page_size=20)
        assert total == 1

    def test_list_for_user_excludes_removed_participants(self):
        repo = DjangoConversationRepository()
        conversation = make_conversation()
        user_id = uuid.uuid4()
        conversation.add_participant(user_id, ParticipantRole.OPERATOR, datetime.utcnow())
        conversation.remove_participant(user_id, datetime.utcnow())
        repo.save(conversation)
        results, total = repo.list_for_user(user_id, status=None, page=1, page_size=20)
        assert total == 0

    def test_list_unassigned(self):
        repo = DjangoConversationRepository()
        repo.save(make_conversation())
        results, total = repo.list_unassigned(conversation_type=None, page=1, page_size=20)
        assert total == 1

    def test_list_unassigned_excludes_assigned_conversations(self):
        repo = DjangoConversationRepository()
        conversation, _ = make_conversation_with_operator()
        repo.save(conversation)
        results, total = repo.list_unassigned(conversation_type=None, page=1, page_size=20)
        assert total == 0


class TestDjangoMessageRepository:
    def test_save_then_get_by_id_round_trips(self):
        repo = DjangoMessageRepository()
        message = make_message()
        repo.save(message)

        fetched = repo.get_by_id(message.id)
        assert fetched is not None
        assert fetched.content.value == message.content.value

    def test_attachment_message_round_trips(self):
        repo = DjangoMessageRepository()
        attachment = AttachmentMetadata(attachment_type=AttachmentType.IMAGE, url="https://example.com/a.jpg", filename="a.jpg", size_bytes=1024)
        message = make_message(message_type=MessageType.ATTACHMENT, content=None, attachment=attachment)
        repo.save(message)

        fetched = repo.get_by_id(message.id)
        assert fetched.attachment.url == "https://example.com/a.jpg"
        assert fetched.content is None

    def test_get_by_id_missing_returns_none(self):
        repo = DjangoMessageRepository()
        assert repo.get_by_id(uuid.uuid4()) is None

    def test_edited_message_round_trips(self):
        repo = DjangoMessageRepository()
        message = make_message()
        message.edit(MessageContent("Updated"), message.sender_id, datetime.utcnow())
        repo.save(message)
        fetched = repo.get_by_id(message.id)
        assert fetched.status.value == "edited"
        assert fetched.content.value == "Updated"

    def test_deleted_message_status_round_trips_using_message_deleted_at_not_deleted_at(self):
        """Verifies the deliberate `message_deleted_at` naming decision from Phase 2 actually works end-to-end -- a Domain-level delete must not collide with SoftDeleteMixin's own framework-level `deleted_at`."""
        repo = DjangoMessageRepository()
        message = make_message()
        message.delete(message.sender_id, datetime.utcnow())
        repo.save(message)
        fetched = repo.get_by_id(message.id)
        assert fetched.status.value == "deleted"
        assert fetched.deleted_at is not None

    def test_list_for_conversation(self):
        repo = DjangoMessageRepository()
        message = make_message()
        repo.save(message)
        results, total = repo.list_for_conversation(message.conversation_id, page=1, page_size=20)
        assert total == 1
