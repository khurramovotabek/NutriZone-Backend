"""
Chat Application Services.

Phase 03B's first real Application Service for Chat, closing the
top-priority gap named by this phase's own charter: Send Message.
`Message.send()` (domain factory) and `DjangoMessageRepository.save()`
were both already fully built and tested -- this orchestrates them,
it does not reinvent them.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from django.db import transaction

from apps.chat.application.services._shared import ChatServiceContext
from apps.chat.application.ports import ConversationRepository, MessageRepository
from apps.chat.domain.aggregates import Conversation, Message
from apps.chat.domain.enums import ConversationStatus, MessageType
from apps.chat.domain.value_objects import AttachmentMetadata, MessageContent
from common.exceptions import ConflictError, ResourceNotFound


class SendMessage:
    """
    Ownership (is the caller an active participant of this
    conversation) is deliberately NOT re-checked here -- it is a
    view-layer, object-level concern, already proven safe and already
    enforced by `_assert_active_participant_or_403()` before this
    service is ever called (Phase 03A's own verified pattern, reused
    rather than duplicated). This service's own responsibility is the
    one thing `Message.send()`'s own docstring explicitly disclaims:
    checking whether the parent `Conversation` is actually OPEN.
    """

    def __init__(self, conversation_repo: ConversationRepository, message_repo: MessageRepository, ctx: ChatServiceContext) -> None:
        self._conversation_repo = conversation_repo
        self._message_repo = message_repo
        self._ctx = ctx

    def execute(
        self, conversation_id: uuid.UUID, sender_id: uuid.UUID, message_type: MessageType,
        content: str | None = None, attachment: AttachmentMetadata | None = None, reply_to_message_id: uuid.UUID | None = None,
    ) -> Message:
        conversation = self._conversation_repo.get_by_id(conversation_id)
        if conversation is None:
            raise ResourceNotFound("Conversation not found.")
        if conversation.status != ConversationStatus.OPEN:
            raise ConflictError(f"Cannot send a message to a conversation that is not open (current status: {conversation.status.value}).")

        message_content = MessageContent(content) if content is not None else None
        sent_at = datetime.now(timezone.utc)
        message, event = Message.send(
            message_id=uuid.uuid4(), conversation_id=conversation_id, sender_id=sender_id, message_type=message_type,
            at=sent_at, content=message_content, attachment=attachment, reply_to_message_id=reply_to_message_id,
        )

        # Real, closed gap found live-verifying the inbox real-time
        # feature: `Conversation.record_activity()` -- its own docstring
        # already says it's "called by the Application layer whenever a
        # new Message is sent" -- was never actually called here. Every
        # real message ever sent left `last_activity_at` frozen at
        # conversation-creation time, forever, so the conversation list
        # (sorted/displayed by it) never reflected real activity.
        conversation.record_activity(sent_at)

        # The state-change write and its outbox event must commit
        # together atomically (MIC §7) -- a real, live-verified bug
        # found here: stage_events() asserts an active atomic block
        # must already be open, but this method previously had none
        # at all, so every real call crashed with a 500.
        with transaction.atomic():
            saved = self._message_repo.save(message)
            self._conversation_repo.save(conversation)
            self._ctx.stage_events([("MessageSent", event.to_payload())])

        self._ctx.audit().created(entity_type="Message", entity_id=str(saved.id), after={"conversation_id": str(conversation_id), "message_type": message_type.value})
        self._ctx.metric("chat_messages_sent_total")
        return saved


class MarkConversationRead:
    """
    Read receipts: marks every message the *other* participants sent in
    this conversation as read by `reader_id`, via the Domain's own
    `Message.mark_read()` (a no-op for an already-read message), staging
    one `MessageRead` event per newly-read message. Returns the read time
    and how many messages changed, so the transport can tell the sender
    ("✓✓ read") only when something actually changed. Participation is
    checked by the caller (the socket only accepts active participants),
    exactly like `SendMessage`.
    """

    _BATCH_LIMIT = 500

    def __init__(self, message_repo: MessageRepository, ctx: ChatServiceContext) -> None:
        self._message_repo = message_repo
        self._ctx = ctx

    def execute(self, conversation_id: uuid.UUID, reader_id: uuid.UUID) -> tuple[datetime, int]:
        read_at = datetime.now(timezone.utc)
        unread = self._message_repo.list_unread_from_others(conversation_id, reader_id, self._BATCH_LIMIT)
        events = []
        with transaction.atomic():
            for message in unread:
                event = message.mark_read(read_at)
                if event is not None:
                    self._message_repo.save(message)
                    events.append(("MessageRead", event.to_payload()))
            if events:
                self._ctx.stage_events(events)
        if events:
            self._ctx.metric("chat_messages_read_total", value=len(events))
        return read_at, len(events)
