"""
Application-layer ports (abstract interfaces) for Chat.

**A disclosed, minimal exception, matching the identical precedent
already established in Wallet's/Loyalty's/Reviews' own Phase 2**:
this file's brief requires Infrastructure's repositories to fulfill
Ports, and every prior module in this build places Ports in
`application/ports.py`, never in `infrastructure/`. Two Protocols
exist -- one per certified aggregate root -- since Chat's Domain
deliberately has two independent aggregates (`Conversation`,
`Message`), not one. Zero business logic, zero Application Services,
zero service context. Nothing else in `application/` was touched
this phase.
"""
from __future__ import annotations

import uuid
from typing import Protocol

from apps.chat.domain.aggregates import Conversation, Message


class ConversationRepository(Protocol):
    def get_by_id(self, conversation_id: uuid.UUID) -> Conversation | None: ...

    def save(self, conversation: Conversation) -> Conversation: ...

    def list_for_user(self, user_id: uuid.UUID, status: str | None, page: int, page_size: int) -> tuple[list[Conversation], int]: ...

    def list_unassigned(self, conversation_type: str | None, page: int, page_size: int) -> tuple[list[Conversation], int]: ...


class MessageRepository(Protocol):
    def get_by_id(self, message_id: uuid.UUID) -> Message | None: ...

    def save(self, message: Message) -> Message: ...

    def list_for_conversation(self, conversation_id: uuid.UUID, page: int, page_size: int) -> tuple[list[Message], int]: ...

    def list_unread_from_others(self, conversation_id: uuid.UUID, reader_id: uuid.UUID, limit: int) -> list[Message]: ...
