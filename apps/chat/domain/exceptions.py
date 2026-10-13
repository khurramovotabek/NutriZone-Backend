"""
Chat domain exceptions.
"""
from __future__ import annotations

from common.exceptions import BusinessRuleViolation, ConflictError, ValidationFailed


class InvalidConversationTransition(ConflictError):
    """The general fallback for any wrong-state conversation transition (close from non-OPEN, reopen from ARCHIVED, etc.)."""

    code = "INVALID_CONVERSATION_TRANSITION"


class ParticipantAlreadyExists(ConflictError):
    code = "PARTICIPANT_ALREADY_EXISTS"


class ParticipantNotFound(ValidationFailed):
    code = "PARTICIPANT_NOT_FOUND"


class InvalidParticipantRole(ValidationFailed):
    """Raised when a role conflicts with the conversation's type -- e.g. attempting to add a CUSTOMER participant to an INTERNAL_SUPPORT conversation."""

    code = "INVALID_PARTICIPANT_ROLE"


class EmptyMessageContent(ValidationFailed):
    code = "EMPTY_MESSAGE_CONTENT"


class MessageContentTooLong(ValidationFailed):
    code = "MESSAGE_CONTENT_TOO_LONG"


class UnknownSticker(ValidationFailed):
    """A STICKER message whose content is not one of the published sticker codes."""


class InvalidCardReference(ValidationFailed):
    """A CARD message whose content is not "product:<uuid>" or "order:<uuid>"."""


class AttachmentRequired(ValidationFailed):
    """Raised when a message of type ATTACHMENT is sent with no attachment metadata."""

    code = "ATTACHMENT_REQUIRED"


class MessageEditNotAllowed(BusinessRuleViolation):
    """Covers both wrong-type (non-TEXT) and wrong-status (not SENT/EDITED) edit attempts."""

    code = "MESSAGE_EDIT_NOT_ALLOWED"


class MessageAlreadyDeleted(ConflictError):
    code = "MESSAGE_ALREADY_DELETED"


class MessageNotOwnedBySender(BusinessRuleViolation):
    """Raised when an edit/delete is attempted by anyone other than the message's own sender -- the one genuinely Domain-enforceable ownership rule, since it needs no cross-aggregate coordination."""

    code = "MESSAGE_NOT_OWNED_BY_SENDER"
