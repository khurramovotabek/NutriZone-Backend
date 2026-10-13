"""
Chat aggregates.

**Two aggregate roots, deliberately, not one** -- `Conversation` and
`Message`. This is Option D from this phase's own list of possible
boundaries ("Conversation + Message as separate aggregates linked by
IDs"), chosen explicitly, not by convenience: Message creation is
high-frequency and does not need the full conversation/message
history loaded for correctness (unlike, say, Wallet's Ledger, where
balance genuinely must be derived by summing every entry). Loading
an entire conversation's message history just to append one new
message would not scale. `Message.conversation_id` is a plain
`uuid.UUID`, the identical intra-module cross-aggregate reference
pattern already established by Wallet's `Cashback.wallet_id`.

**A direct, disclosed consequence of this boundary**: `Message`
cannot check whether its parent `Conversation` is OPEN before being
sent -- that cross-aggregate invariant belongs to the Application
layer (which will load both aggregates and coordinate the check in a
future phase), not to one aggregate reaching into another. `Message.
send()` therefore does not itself enforce "conversation must be
open." This mirrors the exact pattern already established for
Reviews' `verified_purchase` (externally supplied fact) and Wallet's
`Cashback.award()` (does not itself credit the Wallet).

Every mutation happens through a public method; the Application layer
never reaches into a private (underscore-prefixed) method or field --
the same lesson applied directly from the real bug found and fixed in
Wallet Phase 2 (`Wallet._idempotency_index`). Neither aggregate here
stores a field that isn't either a plain public attribute or a plain
dict keyed by entity id.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.chat.domain.entities import Participant
from apps.chat.domain.enums import ConversationStatus, ConversationType, MessageStatus, MessageType, ParticipantRole
from apps.chat.domain.events import (
    ConversationArchivedEvent, ConversationAssigned, ConversationClosedEvent, ConversationOpened, ConversationReopened,
    MessageDeleted, MessageDelivered, MessageEdited, MessageRead, MessageSent, ParticipantAdded, ParticipantRemoved,
)
from apps.chat.domain.exceptions import (
    AttachmentRequired, EmptyMessageContent, InvalidConversationTransition, InvalidParticipantRole,
    MessageAlreadyDeleted, MessageEditNotAllowed, MessageNotOwnedBySender, ParticipantAlreadyExists,
    InvalidCardReference, ParticipantNotFound, UnknownSticker,
)
from apps.chat.domain.services import MessageEditPolicy, ParticipantPolicy
from apps.chat.domain.value_objects import CARD_REF, STICKER_CODES, AttachmentMetadata, ConversationVersion, MessageContent, MessageVersion


@dataclass(slots=True)
class Conversation:
    """Aggregate root -- lifecycle and participant management. Owns `Participant` entities directly (small cardinality, unlike Message)."""

    id: uuid.UUID
    conversation_type: ConversationType
    status: ConversationStatus = ConversationStatus.OPEN
    version: ConversationVersion = field(default_factory=lambda: ConversationVersion(1))
    participants: dict[uuid.UUID, Participant] = field(default_factory=dict)
    assigned_operator_id: uuid.UUID | None = None
    last_activity_at: datetime | None = None
    created_at: datetime | None = None
    store_id: uuid.UUID | None = None
    """Set only for CUSTOMER_SALES conversations opened via `OpenStoreConversation` -- which real store's owner the customer is talking to. A plain UUID reference (apps.stores.Store), never a real ForeignKey, matching every other cross-app reference in this codebase. Conversations opened through the generic `OpenConversation` path (support/internal) legitimately have no store, hence optional."""

    # --- Internal helpers ------------------------------------------------

    def _bump_version(self) -> None:
        self.version = self.version.next()

    def _find_active_participant_by_user_id(self, user_id: uuid.UUID) -> Participant | None:
        return next((p for p in self.participants.values() if p.user_id == user_id and p.is_active), None)

    # --- Creation ----------------------------------------------------------

    @staticmethod
    def open(conversation_id: uuid.UUID, conversation_type: ConversationType, opened_by: uuid.UUID, opener_role: ParticipantRole, at: datetime, store_id: uuid.UUID | None = None) -> tuple["Conversation", ConversationOpened]:
        """
        Opens a new conversation with exactly one initiating
        participant. Whether a conversation ultimately needs "at
        least two participants" (e.g. an operator) before it can be
        meaningfully used is deliberately NOT enforced here -- a
        support conversation legitimately starts with only a
        customer and sits unassigned until an operator picks it up
        (a real, common support-queue pattern), so requiring two
        participants at creation time would be incorrect, not just
        stricter.
        """
        if not ParticipantPolicy.is_role_valid_for_conversation_type(opener_role, conversation_type):
            raise InvalidParticipantRole(f"Role {opener_role.value} is not valid for conversation type {conversation_type.value}.")

        conversation = Conversation(id=conversation_id, conversation_type=conversation_type, created_at=at, last_activity_at=at, store_id=store_id)
        participant = Participant(id=uuid.uuid4(), user_id=opened_by, role=opener_role, joined_at=at)
        conversation.participants[participant.id] = participant
        event = ConversationOpened(conversation_id=conversation.id, conversation_type=conversation_type.value, opened_by=opened_by)
        return conversation, event

    # --- Participants -----------------------------------------------------

    def add_participant(self, user_id: uuid.UUID, role: ParticipantRole, at: datetime) -> ParticipantAdded:
        if not ParticipantPolicy.is_role_valid_for_conversation_type(role, self.conversation_type):
            raise InvalidParticipantRole(f"Role {role.value} is not valid for conversation type {self.conversation_type.value}.")
        if self._find_active_participant_by_user_id(user_id) is not None:
            raise ParticipantAlreadyExists(f"User '{user_id}' is already an active participant in this conversation.")

        participant = Participant(id=uuid.uuid4(), user_id=user_id, role=role, joined_at=at)
        self.participants[participant.id] = participant
        self._bump_version()
        return ParticipantAdded(conversation_id=self.id, participant_id=participant.id, user_id=user_id, role=role.value)

    def remove_participant(self, user_id: uuid.UUID, at: datetime) -> ParticipantRemoved:
        participant = self._find_active_participant_by_user_id(user_id)
        if participant is None:
            raise ParticipantNotFound(f"User '{user_id}' is not an active participant in this conversation.")
        participant.removed_at = at
        self._bump_version()
        return ParticipantRemoved(conversation_id=self.id, participant_id=participant.id)

    # --- Operator assignment -----------------------------------------------

    def assign_operator(self, operator_user_id: uuid.UUID) -> ConversationAssigned:
        """Reassignment is allowed -- calling this again with a different operator simply reassigns; no `ConversationAlreadyAssigned` guard exists, since reassignment is an explicitly supported, ordinary operation, not an error case."""
        self.assigned_operator_id = operator_user_id
        self._bump_version()
        return ConversationAssigned(conversation_id=self.id, operator_id=operator_user_id)

    # --- Lifecycle -----------------------------------------------------------

    def close(self) -> ConversationClosedEvent:
        if self.status != ConversationStatus.OPEN:
            raise InvalidConversationTransition(f"Cannot close a conversation in status {self.status.value}; only OPEN conversations can be closed.")
        self.status = ConversationStatus.CLOSED
        self._bump_version()
        return ConversationClosedEvent(conversation_id=self.id)

    def reopen(self) -> ConversationReopened:
        """ARCHIVED conversations can never be reopened -- archive is deliberately terminal, distinct from close, which is resumable. This is a real, disclosed boundary decision (this phase's own Step 1 found no repository evidence dictating either choice, so this is the documented resolution, not a fabricated certainty)."""
        if self.status != ConversationStatus.CLOSED:
            raise InvalidConversationTransition(f"Cannot reopen a conversation in status {self.status.value}; only CLOSED conversations can be reopened.")
        self.status = ConversationStatus.OPEN
        self._bump_version()
        return ConversationReopened(conversation_id=self.id)

    def archive(self) -> ConversationArchivedEvent:
        if self.status == ConversationStatus.ARCHIVED:
            raise InvalidConversationTransition("This conversation is already archived.")
        self.status = ConversationStatus.ARCHIVED
        self._bump_version()
        return ConversationArchivedEvent(conversation_id=self.id)

    def record_activity(self, at: datetime) -> None:
        """Called by the Application layer whenever a new Message is sent into this conversation, to keep `last_activity_at` current without Conversation ever loading Message data itself. Intentionally emits no event -- this is a lightweight bookkeeping update, not a meaningful business transition in its own right."""
        self.last_activity_at = at
        self._bump_version()


@dataclass(slots=True)
class Message:
    """Aggregate root -- an individual message. `conversation_id` is a plain `uuid.UUID` reference (see this module's own docstring for the full boundary rationale)."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    sender_id: uuid.UUID
    message_type: MessageType
    content: MessageContent | None = None
    attachment: AttachmentMetadata | None = None
    reply_to_message_id: uuid.UUID | None = None
    status: MessageStatus = MessageStatus.SENT
    version: MessageVersion = field(default_factory=lambda: MessageVersion(1))
    created_at: datetime | None = None
    edited_at: datetime | None = None
    deleted_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None

    def _bump_version(self) -> None:
        self.version = self.version.next()

    # --- Creation ----------------------------------------------------------

    @staticmethod
    def send(message_id: uuid.UUID, conversation_id: uuid.UUID, sender_id: uuid.UUID, message_type: MessageType, at: datetime, content: MessageContent | None = None, attachment: AttachmentMetadata | None = None, reply_to_message_id: uuid.UUID | None = None) -> tuple["Message", MessageSent]:
        """
        Content is required for TEXT and SYSTEM messages; attachment
        metadata is required for ATTACHMENT messages (content is then
        optional, serving as an attachment caption); a STICKER message's
        content must be one of the published STICKER_CODES. Does NOT check
        whether the parent Conversation is open -- see this module's
        own docstring for why that cross-aggregate check is out of
        scope here. Does NOT enforce any distributed-system
        idempotency/duplicate-detection guarantee -- that is
        explicitly an Infrastructure/Application concern (e.g. a
        client-supplied idempotency key handled at the API layer),
        not something Domain can honestly provide on its own.
        """
        if message_type in (MessageType.TEXT, MessageType.SYSTEM) and content is None:
            raise EmptyMessageContent(f"{message_type.value} messages require content.")
        if message_type == MessageType.ATTACHMENT and attachment is None:
            raise AttachmentRequired("ATTACHMENT messages require attachment metadata.")
        if message_type == MessageType.STICKER and (content is None or content.value not in STICKER_CODES):
            raise UnknownSticker("STICKER messages require one of the published sticker codes as content.", details={"fields": [{"field": "content", "code": "UNKNOWN_STICKER"}]})
        if message_type == MessageType.CARD and (content is None or not CARD_REF.match(content.value)):
            raise InvalidCardReference("CARD messages require content like product:<uuid> or order:<uuid>.", details={"fields": [{"field": "content", "code": "INVALID_CARD"}]})

        message = Message(id=message_id, conversation_id=conversation_id, sender_id=sender_id, message_type=message_type, content=content, attachment=attachment, reply_to_message_id=reply_to_message_id, created_at=at)
        event = MessageSent(message_id=message.id, conversation_id=conversation_id, sender_id=sender_id, message_type=message_type.value)
        return message, event

    # --- Editing / Deletion --------------------------------------------------

    def edit(self, new_content: MessageContent, requested_by: uuid.UUID, at: datetime) -> MessageEdited:
        if requested_by != self.sender_id:
            raise MessageNotOwnedBySender("Only the original sender may edit this message.")
        if not MessageEditPolicy.can_edit(self.message_type.value, self.status.value):
            raise MessageEditNotAllowed(f"A {self.message_type.value} message in status {self.status.value} cannot be edited.")
        self.content = new_content
        self.status = MessageStatus.EDITED
        self.edited_at = at
        self._bump_version()
        return MessageEdited(message_id=self.id, conversation_id=self.conversation_id)

    def delete(self, requested_by: uuid.UUID, at: datetime) -> MessageDeleted:
        if requested_by != self.sender_id:
            raise MessageNotOwnedBySender("Only the original sender may delete this message.")
        if self.status == MessageStatus.DELETED:
            raise MessageAlreadyDeleted("This message has already been deleted.")
        self.status = MessageStatus.DELETED
        self.deleted_at = at
        self._bump_version()
        return MessageDeleted(message_id=self.id, conversation_id=self.conversation_id)

    # --- Delivery / Read state -----------------------------------------------

    def mark_delivered(self, at: datetime) -> MessageDelivered | None:
        """A legitimate no-op if already delivered -- matching the established 'a repeated signal is a safe no-op, not an error' precedent (e.g. `apps.loyalty.domain.aggregates.LoyaltyMembership.evaluate_tier`'s own no-change case), since a WebSocket delivery acknowledgment may genuinely arrive more than once."""
        if self.delivered_at is not None:
            return None
        self.delivered_at = at
        self._bump_version()
        return MessageDelivered(message_id=self.id)

    def mark_read(self, at: datetime) -> MessageRead | None:
        if self.read_at is not None:
            return None
        self.read_at = at
        self._bump_version()
        return MessageRead(message_id=self.id)
