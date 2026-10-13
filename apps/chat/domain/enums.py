"""
Chat domain enums.

`chat` is Domain Architecture Specification §2.12, confirmed by
reading the module's own placeholder scaffold before any code was
written (its README cited that section explicitly).
"""
from __future__ import annotations

from common.utils import DomainStrEnum


class ConversationType(DomainStrEnum):
    """The three categories named in this module's own context brief -- no speculative fourth type added."""

    CUSTOMER_SALES = "customer_sales"
    CUSTOMER_SUPPORT = "customer_support"
    INTERNAL_SUPPORT = "internal_support"


class ConversationStatus(DomainStrEnum):
    """ARCHIVED is deliberately terminal -- see aggregates.py's own `reopen()` docstring for the full rationale (archive means permanently done; close means temporarily done and resumable)."""

    OPEN = "open"
    CLOSED = "closed"
    ARCHIVED = "archived"


class ParticipantRole(DomainStrEnum):
    CUSTOMER = "customer"
    OPERATOR = "operator"


class MessageType(DomainStrEnum):
    TEXT = "text"
    ATTACHMENT = "attachment"
    SYSTEM = "system"
    STICKER = "sticker"  # content = one code from value_objects.STICKER_CODES
    CARD = "card"  # content = "product:<uuid>" or "order:<uuid>" -- rendered as a product / order card (value_objects.CARD_REF)


class MessageStatus(DomainStrEnum):
    """DELETED is terminal -- no further edits are possible, matching this build's established soft-deletion conventions (a deleted message is marked, never hard-removed)."""

    SENT = "sent"
    EDITED = "edited"
    DELETED = "deleted"


class AttachmentType(DomainStrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"
