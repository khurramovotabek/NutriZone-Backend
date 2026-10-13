"""
Test factories for Reviews domain objects -- keeps every test file's
Arrange step short and consistent. Every factory accepts overrides
via **kwargs so individual tests can vary just the field under test.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from apps.reviews.domain.aggregates import Review
from apps.reviews.domain.value_objects import Rating, ReviewBody, ReviewTitle


def make_review(**overrides) -> Review:
    defaults = dict(
        id=uuid.uuid4(), product_id=uuid.uuid4(), customer_id=uuid.uuid4(), rating=Rating(5),
        body=ReviewBody("This product exceeded my expectations."), verified_purchase=True,
        title=ReviewTitle("Great product"), created_at=datetime.utcnow(),
    )
    defaults.update(overrides)
    return Review(**defaults)


def make_published_review(**overrides) -> Review:
    """A review already carried through submit->approve->publish -- avoids every test that needs a PUBLISHED starting point re-deriving the same 3-call sequence."""
    review = make_review(**overrides)
    now = datetime.utcnow()
    review.submit(now)
    review.approve(now)
    review.publish(now)
    return review
