"""
Reviews domain entities (non-root members of Review).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from apps.reviews.domain.enums import ReviewMediaType
from common.exceptions import ValidationFailed


@dataclass(slots=True)
class ReviewMedia:
    """
    Non-root entity, owned by Review -- has independent identity
    because a customer can plausibly reference or reason about one
    specific photo/video among several attached to the same review
    (this is the concrete reason it is an entity, not a value
    object -- see value_objects.py's own module docstring for the
    full "why not a VO" account).
    """

    id: uuid.UUID
    media_type: ReviewMediaType
    url: str
    uploaded_at: datetime

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValidationFailed("ReviewMedia url must not be empty.", details={"fields": [{"field": "url", "code": "EMPTY"}]})
