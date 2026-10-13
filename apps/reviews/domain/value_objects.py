"""
Reviews domain value objects.

**A deliberate, disclosed departure from this phase's own "potential
concepts" list**: no `ReviewIdentifier`, `ProductReference`, or
`CustomerReference` wrapper value objects are defined. Every prior
module in this build (Wallet's `customer_id`, Loyalty's
`customer_id`) references another bounded context's aggregate by a
plain `uuid.UUID`, never a dedicated wrapper VO -- and `Products`
itself (the real, implemented module that owns product identity,
confirmed by inspection during Step 1) uses a plain `uuid.UUID` for
its own `Product.id`. Introducing wrapper types here would be
inconsistent with that established, repository-wide convention, not
a richer design. `Review.id`, `product_id`, and `customer_id` are all
plain `uuid.UUID` fields (see aggregates.py).

Also deliberately absent: a `MediaReference` value object. Review
media needs independent identity (a customer can plausibly reference
one specific photo among several), so it is modeled as the
`ReviewMedia` entity instead (see entities.py) -- a value object
would not fit "has independent identity," and creating one anyway
merely to satisfy this phase's suggested-concepts list would violate
its own "do not create speculative" instruction.

Also deliberately absent: a `ReviewNumber`-style factory-generated
business code (the pattern used by every prior module's aggregate --
`OrderNumber`, `WalletMembershipNumber`, etc.). Reviews are addressed
by UUID in every realistic API shape (`GET /reviews/{id}`); unlike an
order or a wallet, there is no real business need for a customer- or
support-facing human-readable review code. Adding one would be
speculative.
"""
from __future__ import annotations

from dataclasses import dataclass

from apps.reviews.domain.exceptions import InvalidRating, ReviewContentTooLong
from common.exceptions import ValidationFailed

MIN_RATING = 1
MAX_RATING = 5
MAX_TITLE_LENGTH = 150
MAX_BODY_LENGTH = 5000


@dataclass(frozen=True, slots=True)
class Rating:
    """A single review's star rating. Domain boundary is explicit and inclusive on both ends: 1 is valid, 5 is valid, 0 and 6 are not."""

    value: int

    def __post_init__(self) -> None:
        if not (MIN_RATING <= self.value <= MAX_RATING):
            raise InvalidRating(f"Rating must be between {MIN_RATING} and {MAX_RATING} inclusive (got {self.value}).", details={"fields": [{"field": "rating", "code": "OUT_OF_RANGE"}]})


@dataclass(frozen=True, slots=True)
class ReviewTitle:
    """Optional in the aggregate (title=None is valid), but if a title IS supplied, this VO enforces it is non-empty and within bounds -- 'optional' and 'invalid empty string' are different things."""

    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValidationFailed("ReviewTitle must not be empty or whitespace-only.", details={"fields": [{"field": "title", "code": "EMPTY"}]})
        if len(self.value) > MAX_TITLE_LENGTH:
            raise ReviewContentTooLong(f"ReviewTitle must not exceed {MAX_TITLE_LENGTH} characters (got {len(self.value)}).", details={"fields": [{"field": "title", "code": "TOO_LONG"}]})


@dataclass(frozen=True, slots=True)
class ReviewBody:
    """Required -- every Review must have a non-empty body, per this module's own aggregate design (see aggregates.py's `Review.create()`)."""

    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValidationFailed("ReviewBody must not be empty or whitespace-only.", details={"fields": [{"field": "body", "code": "EMPTY"}]})
        if len(self.value) > MAX_BODY_LENGTH:
            raise ReviewContentTooLong(f"ReviewBody must not exceed {MAX_BODY_LENGTH} characters (got {len(self.value)}).", details={"fields": [{"field": "body", "code": "TOO_LONG"}]})


@dataclass(frozen=True, slots=True)
class ReviewVersion:
    """Optimistic-locking version counter -- same rationale as `apps.wallet.domain.value_objects.WalletVersion` / `apps.loyalty.domain.value_objects.MembershipVersion`."""

    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise ValidationFailed("Review version must be at least 1.")

    def next(self) -> "ReviewVersion":
        return ReviewVersion(self.value + 1)
