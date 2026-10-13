"""
Composition root for the `chat` module.

Phase 03B closed the previously-real "zero Application Services" gap
(disclosed accurately by this module's own docstring across Phases
2 and 03A): `SendMessage` is the first real Application Service for
Chat, orchestrating already-existing, already-tested domain logic
(`Message.send()`) and repository (`DjangoMessageRepository.save()`)
that were simply never wired to a caller before this phase.
"""
from __future__ import annotations

from apps.chat.application.services._shared import ChatServiceContext
from apps.chat.application.services.conversations import (
    AddParticipant,
    ArchiveConversation,
    AssignOperator,
    CloseConversation,
    OpenConversation,
    OpenStoreConversation,
    RemoveParticipant,
    ReopenConversation,
)
from apps.chat.application.services.messages import MarkConversationRead, SendMessage
from apps.chat.infrastructure.gateways import NotImplementedNotificationGateway, RealMediaStorageGateway
from apps.chat.infrastructure.models import ChatOutboxEvent
from apps.chat.infrastructure.repositories import DjangoConversationRepository, DjangoMessageRepository
from apps.chat.infrastructure.selectors import ChatStatisticsSelector, ConversationSelector, CustomerProfileSelector, MessageSelector
from core.outbox import stage_event


def stage_chat_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(ChatOutboxEvent, event_type, payload)


def build_chat_service_context(actor_id=None) -> ChatServiceContext:
    return ChatServiceContext(stage_events=stage_chat_events, actor_id=actor_id)


def build_send_message(actor_id=None) -> SendMessage:
    return SendMessage(DjangoConversationRepository(), DjangoMessageRepository(), build_chat_service_context(actor_id))


def build_mark_conversation_read(actor_id=None) -> MarkConversationRead:
    return MarkConversationRead(DjangoMessageRepository(), build_chat_service_context(actor_id))


def build_open_conversation(actor_id=None) -> OpenConversation:
    return OpenConversation(DjangoConversationRepository(), build_chat_service_context(actor_id))


def build_open_store_conversation(actor_id=None) -> OpenStoreConversation:
    return OpenStoreConversation(DjangoConversationRepository(), build_chat_service_context(actor_id))


def build_add_participant(actor_id=None) -> AddParticipant:
    return AddParticipant(DjangoConversationRepository(), build_chat_service_context(actor_id))


def build_remove_participant(actor_id=None) -> RemoveParticipant:
    return RemoveParticipant(DjangoConversationRepository(), build_chat_service_context(actor_id))


def build_assign_operator(actor_id=None) -> AssignOperator:
    return AssignOperator(DjangoConversationRepository(), build_chat_service_context(actor_id))


def build_close_conversation(actor_id=None) -> CloseConversation:
    return CloseConversation(DjangoConversationRepository(), build_chat_service_context(actor_id))


def build_reopen_conversation(actor_id=None) -> ReopenConversation:
    return ReopenConversation(DjangoConversationRepository(), build_chat_service_context(actor_id))


def build_archive_conversation(actor_id=None) -> ArchiveConversation:
    return ArchiveConversation(DjangoConversationRepository(), build_chat_service_context(actor_id))


def build_conversation_repository() -> DjangoConversationRepository:
    return DjangoConversationRepository()


def build_message_repository() -> DjangoMessageRepository:
    return DjangoMessageRepository()


def build_conversation_selector() -> ConversationSelector:
    return ConversationSelector()


def build_message_selector() -> MessageSelector:
    return MessageSelector()


def build_chat_statistics_selector() -> ChatStatisticsSelector:
    return ChatStatisticsSelector()


def build_customer_profile_selector() -> CustomerProfileSelector:
    return CustomerProfileSelector()


def build_notification_gateway() -> NotImplementedNotificationGateway:
    return NotImplementedNotificationGateway()


def build_media_storage_gateway() -> RealMediaStorageGateway:
    return RealMediaStorageGateway()
