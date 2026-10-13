"""
Chat domain events.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ConversationOpened:
    conversation_id: uuid.UUID
    conversation_type: str
    opened_by: uuid.UUID

    def to_payload(self) -> dict:
        return {**asdict(self), "conversation_id": str(self.conversation_id), "opened_by": str(self.opened_by)}


@dataclass(frozen=True, slots=True)
class ParticipantAdded:
    conversation_id: uuid.UUID
    participant_id: uuid.UUID
    user_id: uuid.UUID
    role: str

    def to_payload(self) -> dict:
        return {**asdict(self), "conversation_id": str(self.conversation_id), "participant_id": str(self.participant_id), "user_id": str(self.user_id)}


@dataclass(frozen=True, slots=True)
class ParticipantRemoved:
    conversation_id: uuid.UUID
    participant_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"conversation_id": str(self.conversation_id), "participant_id": str(self.participant_id)}


@dataclass(frozen=True, slots=True)
class ConversationAssigned:
    conversation_id: uuid.UUID
    operator_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"conversation_id": str(self.conversation_id), "operator_id": str(self.operator_id)}


@dataclass(frozen=True, slots=True)
class ConversationClosedEvent:
    """Named with an Event suffix, matching this build's established defensive-naming convention -- avoids any future near-miss against a plausible `ConversationClosed`-named exception."""

    conversation_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"conversation_id": str(self.conversation_id)}


@dataclass(frozen=True, slots=True)
class ConversationReopened:
    conversation_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"conversation_id": str(self.conversation_id)}


@dataclass(frozen=True, slots=True)
class ConversationArchivedEvent:
    conversation_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"conversation_id": str(self.conversation_id)}


@dataclass(frozen=True, slots=True)
class MessageSent:
    message_id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID
    message_type: str

    def to_payload(self) -> dict:
        return {**asdict(self), "message_id": str(self.message_id), "conversation_id": str(self.conversation_id), "sender_id": str(self.sender_id)}


@dataclass(frozen=True, slots=True)
class MessageEdited:
    message_id: uuid.UUID
    conversation_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"message_id": str(self.message_id), "conversation_id": str(self.conversation_id)}


@dataclass(frozen=True, slots=True)
class MessageDeleted:
    message_id: uuid.UUID
    conversation_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"message_id": str(self.message_id), "conversation_id": str(self.conversation_id)}


@dataclass(frozen=True, slots=True)
class MessageDelivered:
    message_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"message_id": str(self.message_id)}


@dataclass(frozen=True, slots=True)
class MessageRead:
    message_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"message_id": str(self.message_id)}
