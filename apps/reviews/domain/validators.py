"""
Reviews domain validators -- thin, intention-revealing wrappers over
value object constructors, matching every prior module's
domain/validators.py pattern.
"""
from __future__ import annotations

from apps.reviews.domain.value_objects import Rating, ReviewBody, ReviewTitle


def RatingValidator(value: int) -> Rating:  # noqa: N802
    return Rating(value)


def ReviewTitleValidator(value: str) -> ReviewTitle:  # noqa: N802
    return ReviewTitle(value)


def ReviewBodyValidator(value: str) -> ReviewBody:  # noqa: N802
    return ReviewBody(value)
