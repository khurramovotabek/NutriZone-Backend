"""
Chat domain services -- pure business rules with no I/O, per MIC §4,
matching every prior module's domain/services.py pattern.

**A deliberate scope decision, disclosed rather than silently
assumed**: no `ConversationAssignmentPolicy` or `ConversationRoutingPolicy`
is defined, despite being listed as "potential examples" in this
phase's own brief. Deciding WHICH operator to assign (round-robin,
least-busy, skill-based routing) genuinely requires knowledge of
other conversations and operators' current workload -- that is
repository/cross-aggregate knowledge, which cannot be a pure Domain
service without either faking that knowledge or reaching outside the
aggregate boundary. This capability's correct home is Application/
Infrastructure in a future phase, not Domain now.
"""
from __future__ import annotations

from apps.chat.domain.enums import ConversationType, ParticipantRole


class MessageEditPolicy:
    """Pure decision: given a message's current type and status, is editing currently allowed? Used both by `Message.edit()` itself and potentially by a future Application-layer permission pre-check, so it is kept as an independently testable unit rather than inlined -- the same reasoning already established for `apps.reviews.domain.services.ReviewEditPolicy`."""

    _EDITABLE_TYPES = ("text",)
    _EDITABLE_STATUSES = ("sent", "edited")

    @staticmethod
    def can_edit(message_type: str, status: str) -> bool:
        return message_type in MessageEditPolicy._EDITABLE_TYPES and status in MessageEditPolicy._EDITABLE_STATUSES


class ParticipantPolicy:
    """Pure decision: is this role valid for this conversation type? INTERNAL_SUPPORT conversations never have a CUSTOMER participant; CUSTOMER_SALES/CUSTOMER_SUPPORT conversations may have both roles."""

    @staticmethod
    def is_role_valid_for_conversation_type(role: ParticipantRole, conversation_type: ConversationType) -> bool:
        if conversation_type == ConversationType.INTERNAL_SUPPORT:
            return role == ParticipantRole.OPERATOR
        return True
