"""
Chat domain entities (non-root members of Conversation).

**Only one entity exists**: `Participant`. `Message` is deliberately
NOT modeled here as an owned entity -- it is a separate aggregate
root (see aggregates.py's own docstring for the full reasoning on
this boundary). Participant cardinality per conversation is small
(a handful of people, not thousands), unlike Message's high-frequency
creation pattern, so owning it directly within Conversation does not
create the same scaling concern.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from apps.chat.domain.enums import ParticipantRole


@dataclass(slots=True)
class Participant:
    """
    Non-root entity, owned by Conversation -- has independent
    identity because a participant can be individually added,
    removed (soft, via `removed_at`), and referenced without needing
    the full conversation history.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    role: ParticipantRole
    joined_at: datetime
    removed_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.removed_at is None
