from __future__ import annotations

import ast
import dataclasses
import uuid

import pytest

import apps.reviews.domain.events as events_module
import apps.reviews.domain.exceptions as exceptions_module
from apps.reviews.domain.events import (
    ReviewApproved, ReviewCreated, ReviewEdited, ReviewHidden, ReviewMediaAttached, ReviewPublished, ReviewRejected,
    ReviewSubmitted, ReviewWithdrawn,
)

pytestmark = pytest.mark.unit


def test_review_created_payload():
    review_id, product_id, customer_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    payload = ReviewCreated(review_id=review_id, product_id=product_id, customer_id=customer_id).to_payload()
    assert payload["review_id"] == str(review_id)
    assert payload["product_id"] == str(product_id)


def test_review_submitted_payload():
    review_id, product_id = uuid.uuid4(), uuid.uuid4()
    payload = ReviewSubmitted(review_id=review_id, product_id=product_id).to_payload()
    assert payload["review_id"] == str(review_id)


def test_review_approved_payload():
    review_id = uuid.uuid4()
    assert ReviewApproved(review_id=review_id).to_payload() == {"review_id": str(review_id)}


def test_review_rejected_payload():
    payload = ReviewRejected(review_id=uuid.uuid4(), reason="spam").to_payload()
    assert payload["reason"] == "spam"


def test_review_published_payload():
    payload = ReviewPublished(review_id=uuid.uuid4(), product_id=uuid.uuid4(), rating=5).to_payload()
    assert payload["rating"] == 5


def test_review_hidden_payload():
    payload = ReviewHidden(review_id=uuid.uuid4(), reason="customer_complaint").to_payload()
    assert payload["reason"] == "customer_complaint"


def test_review_edited_payload_carries_remoderation_flag():
    payload = ReviewEdited(review_id=uuid.uuid4(), reset_to_pending_moderation=True).to_payload()
    assert payload["reset_to_pending_moderation"] is True


def test_review_withdrawn_payload():
    review_id = uuid.uuid4()
    assert ReviewWithdrawn(review_id=review_id).to_payload() == {"review_id": str(review_id)}


def test_review_media_attached_payload():
    payload = ReviewMediaAttached(review_id=uuid.uuid4(), media_id=uuid.uuid4(), media_type="image").to_payload()
    assert payload["media_type"] == "image"


def test_every_event_is_a_frozen_dataclass():
    event_classes = [obj for name, obj in vars(events_module).items() if isinstance(obj, type) and dataclasses.is_dataclass(obj)]
    for cls in event_classes:
        assert cls.__dataclass_params__.frozen is True, f"{cls.__name__} is not frozen"


def test_events_are_immutable():
    event = ReviewApproved(review_id=uuid.uuid4())
    with pytest.raises(Exception):
        event.review_id = uuid.uuid4()  # type: ignore[misc]


def test_programmatically_verify_exactly_9_events():
    """AST-parses events.py directly -- matches this build's established exact-count verification pattern."""
    tree = ast.parse(open(events_module.__file__).read())
    class_names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert len(class_names) == 9, f"Expected exactly 9 Reviews domain events, found {len(class_names)}: {class_names}"


def test_zero_collisions_between_events_and_exceptions():
    event_names = set(n.name for n in ast.parse(open(events_module.__file__).read()).body if isinstance(n, ast.ClassDef))
    exception_names = set(n.name for n in ast.parse(open(exceptions_module.__file__).read()).body if isinstance(n, ast.ClassDef))
    collisions = event_names & exception_names
    assert not collisions, f"Naming collisions found between events and exceptions: {collisions}"
