"""
Reviews domain enums.

`reviews` is Domain Architecture Specification §2.11, confirmed by
reading the module's own placeholder scaffold before any code was
written (its README cited that section explicitly).

**A deliberate, disclosed scope decision**: no `ReviewVisibility` enum
is defined, despite being listed as a "potential concept" in this
phase's own brief. `ReviewStatus` already fully captures visibility
implicitly (PUBLISHED is the only visible state) -- a separate,
overlapping enum would be a speculative duplicate of information
`ReviewStatus` already owns, which this phase's own rules forbid
("Do NOT create speculative enums").
"""
from __future__ import annotations

from common.utils import DomainStrEnum


class ReviewStatus(DomainStrEnum):
    """The full lifecycle. DRAFT is the only editable-without-consequence state; editing a PUBLISHED review resets it to PENDING_MODERATION (see aggregates.py's own `edit_content()` docstring for the full rationale)."""

    DRAFT = "draft"
    PENDING_MODERATION = "pending_moderation"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    HIDDEN = "hidden"
    WITHDRAWN = "withdrawn"


class ReviewMediaType(DomainStrEnum):
    IMAGE = "image"
    VIDEO = "video"


class ReviewRejectionReason(DomainStrEnum):
    SPAM = "spam"
    OFFENSIVE_CONTENT = "offensive_content"
    POLICY_VIOLATION = "policy_violation"
    OFF_TOPIC = "off_topic"
    OTHER = "other"


class ReviewHideReason(DomainStrEnum):
    """Distinct from `ReviewRejectionReason` -- hiding acts on an already-PUBLISHED review (a later moderation action, e.g. in response to a complaint), rejecting acts on a PENDING_MODERATION review (the original moderation decision). Conflating them would lose that distinction in the history."""

    POLICY_VIOLATION = "policy_violation"
    CUSTOMER_COMPLAINT = "customer_complaint"
    LEGAL_REQUEST = "legal_request"
    OTHER = "other"
