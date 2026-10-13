"""
Chat repositories.

Concrete implementations of application/ports.py's `ConversationRepository`
and `MessageRepository` Protocols -- maps ORM rows to domain
dataclasses only, never leaks ORM objects outside this module,
matching the pattern established by every prior module.
"""
from __future__ import annotations

import uuid

from django.db import IntegrityError

from apps.chat.domain.aggregates import Conversation, Message
from apps.chat.domain.entities import Participant
from apps.chat.domain.enums import AttachmentType, ConversationStatus, ConversationType, MessageStatus, MessageType, ParticipantRole
from apps.chat.domain.value_objects import AttachmentMetadata, ConversationVersion, MessageContent, MessageVersion
from apps.chat.infrastructure import models as orm
from common.exceptions import ConflictError


class DjangoConversationRepository:
    def get_by_id(self, conversation_id: uuid.UUID) -> Conversation | None:
        row = orm.ConversationModel.objects.filter(id=conversation_id).prefetch_related("participants").first()
        return self._to_domain(row) if row else None

    def save(self, conversation: Conversation) -> Conversation:
        try:
            row, _ = orm.ConversationModel.objects.update_or_create(
                id=conversation.id,
                defaults={
                    "conversation_type": conversation.conversation_type.value, "status": conversation.status.value,
                    "version": conversation.version.value, "assigned_operator_id": conversation.assigned_operator_id,
                    "last_activity_at": conversation.last_activity_at, "store_id": conversation.store_id,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A conversation with conflicting unique fields already exists.") from exc

        existing_participant_ids = set(row.participants.values_list("id", flat=True))
        for participant in conversation.participants.values():
            if participant.id not in existing_participant_ids:
                orm.ParticipantModel.objects.create(id=participant.id, conversation=row, user_id=participant.user_id, role=participant.role.value, joined_at=participant.joined_at, removed_at=participant.removed_at)
            else:
                orm.ParticipantModel.objects.filter(id=participant.id).update(removed_at=participant.removed_at)
        return conversation

    def list_for_user(self, user_id: uuid.UUID, status: str | None, page: int, page_size: int) -> tuple[list[Conversation], int]:
        conversation_ids = orm.ParticipantModel.objects.filter(user_id=user_id, removed_at__isnull=True).values_list("conversation_id", flat=True)
        qs = orm.ConversationModel.objects.filter(id__in=conversation_ids)
        if status:
            qs = qs.filter(status=status)
        total = qs.count()
        rows = qs.order_by("-last_activity_at")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def list_unassigned(self, conversation_type: str | None, page: int, page_size: int) -> tuple[list[Conversation], int]:
        qs = orm.ConversationModel.objects.filter(assigned_operator_id__isnull=True, status=ConversationStatus.OPEN.value)
        if conversation_type:
            qs = qs.filter(conversation_type=conversation_type)
        total = qs.count()
        rows = qs.order_by("created_at")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def _to_domain(self, row: orm.ConversationModel) -> Conversation:
        participants = {}
        for p in row.participants.all():
            participant = Participant(id=p.id, user_id=p.user_id, role=ParticipantRole(p.role), joined_at=p.joined_at, removed_at=p.removed_at)
            participants[participant.id] = participant

        return Conversation(
            id=row.id, conversation_type=ConversationType(row.conversation_type), status=ConversationStatus(row.status),
            version=ConversationVersion(row.version), participants=participants, assigned_operator_id=row.assigned_operator_id,
            last_activity_at=row.last_activity_at, created_at=row.created_at, store_id=row.store_id,
        )


class DjangoMessageRepository:
    def get_by_id(self, message_id: uuid.UUID) -> Message | None:
        row = orm.MessageModel.objects.filter(id=message_id).first()
        return self._to_domain(row) if row else None

    def save(self, message: Message) -> Message:
        try:
            orm.MessageModel.objects.update_or_create(
                id=message.id,
                defaults={
                    "conversation_id": message.conversation_id, "sender_id": message.sender_id, "message_type": message.message_type.value,
                    "content": message.content.value if message.content else None,
                    "attachment_type": message.attachment.attachment_type.value if message.attachment else None,
                    "attachment_url": message.attachment.url if message.attachment else None,
                    "attachment_filename": message.attachment.filename if message.attachment else None,
                    "attachment_size_bytes": message.attachment.size_bytes if message.attachment else None,
                    "reply_to_message_id": message.reply_to_message_id, "status": message.status.value, "version": message.version.value,
                    "edited_at": message.edited_at, "message_deleted_at": message.deleted_at, "delivered_at": message.delivered_at, "read_at": message.read_at,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A message with conflicting unique fields already exists.") from exc
        return message

    def list_for_conversation(self, conversation_id: uuid.UUID, page: int, page_size: int) -> tuple[list[Message], int]:
        qs = orm.MessageModel.objects.filter(conversation_id=conversation_id)
        total = qs.count()
        rows = qs.order_by("created_at")[(page - 1) * page_size : page * page_size]
        return [self._to_domain(r) for r in rows], total

    def list_unread_from_others(self, conversation_id: uuid.UUID, reader_id: uuid.UUID, limit: int) -> list[Message]:
        """Messages in the conversation that someone *else* sent and nobody has marked read yet, oldest first."""
        rows = (
            orm.MessageModel.objects.filter(conversation_id=conversation_id, read_at__isnull=True)
            .exclude(sender_id=reader_id)
            .order_by("created_at")[:limit]
        )
        return [self._to_domain(r) for r in rows]

    def _to_domain(self, row: orm.MessageModel) -> Message:
        attachment = None
        if row.attachment_url:
            attachment = AttachmentMetadata(attachment_type=AttachmentType(row.attachment_type), url=row.attachment_url, filename=row.attachment_filename, size_bytes=row.attachment_size_bytes)

        return Message(
            id=row.id, conversation_id=row.conversation_id, sender_id=row.sender_id, message_type=MessageType(row.message_type),
            content=MessageContent(row.content) if row.content else None, attachment=attachment, reply_to_message_id=row.reply_to_message_id,
            status=MessageStatus(row.status), version=MessageVersion(row.version), created_at=row.created_at, edited_at=row.edited_at,
            deleted_at=row.message_deleted_at, delivered_at=row.delivered_at, read_at=row.read_at,
        )
