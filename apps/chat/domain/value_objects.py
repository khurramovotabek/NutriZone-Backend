"""
Chat domain value objects.

**A deliberate, disclosed departure from this phase's own suggested
concepts list**: no `ConversationId`/`MessageId`/`ParticipantReference`
wrapper value objects are defined. Every prior module in this build
references another aggregate (whether cross-module or, as here,
cross-aggregate within the same module -- see aggregates.py's own
docstring for the Conversation/Message boundary decision) by a plain
`uuid.UUID`. Step 1 confirmed no existing module contradicts this.
`Conversation.id`, `Message.id`, `Message.conversation_id`,
`Message.sender_id`, and `Participant.user_id` are all plain
`uuid.UUID` fields.

Also deliberately absent: `MessageSequence`. True atomic sequence
numbering is a database/infrastructure concern (e.g. a Postgres
sequence or a Redis INCR), not something pure Domain can provide
without inventing a distributed-system guarantee it has no way to
actually keep -- which this phase's own rules explicitly forbid.
Message ordering is `(created_at, id)`, matching the identical
"sorted by occurred_at" convention already used by every other
module's own history/ledger ordering.

Also deliberately absent: a dedicated `ReplyReference` value object.
`Message.reply_to_message_id` is a plain, optional `uuid.UUID` --
there is no additional invariant it carries beyond "which message
(if any) this one replies to," so a wrapper type would add a class
with no real validation logic of its own.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from apps.chat.domain.enums import AttachmentType
from apps.chat.domain.exceptions import EmptyMessageContent, MessageContentTooLong
from common.exceptions import ValidationFailed

MAX_CONTENT_LENGTH = 4000


# The published sticker set: a STICKER message's content must be one of
# these codes (the storefront renders each as its own illustrated card).
# A closed set on purpose -- a sticker is a fixed, curated asset, never
# free text smuggled through a different message type.
#: A CARD message points at a product or an order; the card itself (name, photo, price, status) is resolved when read.
CARD_REF = re.compile(r"^(product|order):[0-9a-fA-F-]{36}$")

STICKER_CODES = frozenset({
    "hello", "thanks", "in_stock", "order_ready", "on_the_way", "delivered",
    "discount", "original", "one_moment", "power", "call_me", "deal",
})


@dataclass(frozen=True, slots=True)
class MessageContent:
    """Required to be non-empty when constructed at all -- `Message` itself decides whether content is required for a given `MessageType` (see aggregates.py's `Message.send()`); this VO only guarantees that if content IS supplied, it is a real, bounded string, not that every message must have one."""

    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise EmptyMessageContent("MessageContent must not be empty or whitespace-only.", details={"fields": [{"field": "content", "code": "EMPTY"}]})
        if len(self.value) > MAX_CONTENT_LENGTH:
            raise MessageContentTooLong(f"MessageContent must not exceed {MAX_CONTENT_LENGTH} characters (got {len(self.value)}).", details={"fields": [{"field": "content", "code": "TOO_LONG"}]})


@dataclass(frozen=True, slots=True)
class AttachmentMetadata:
    """Frozen metadata only -- no file storage, no binary content, no upload logic. `url` is assumed already-uploaded-and-resolvable by the time Domain sees it; the actual upload mechanism is an Infrastructure concern for a future phase."""

    attachment_type: AttachmentType
    url: str
    filename: str
    size_bytes: int

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValidationFailed("AttachmentMetadata url must not be empty.", details={"fields": [{"field": "url", "code": "EMPTY"}]})
        if not self.filename.strip():
            raise ValidationFailed("AttachmentMetadata filename must not be empty.", details={"fields": [{"field": "filename", "code": "EMPTY"}]})
        if self.size_bytes <= 0:
            raise ValidationFailed("AttachmentMetadata size_bytes must be positive.", details={"fields": [{"field": "size_bytes", "code": "OUT_OF_RANGE"}]})


@dataclass(frozen=True, slots=True)
class ConversationVersion:
    """Optimistic-locking version counter -- same rationale as every prior module's own aggregate version VO."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise ValidationFailed("Conversation version must be at least 1.")

    def next(self) -> "ConversationVersion":
        return ConversationVersion(self.value + 1)


@dataclass(frozen=True, slots=True)
class MessageVersion:
    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise ValidationFailed("Message version must be at least 1.")

    def next(self) -> "MessageVersion":
        return MessageVersion(self.value + 1)
