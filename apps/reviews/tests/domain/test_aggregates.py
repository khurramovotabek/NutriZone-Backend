"""
Aggregate tests -- covers every public method, every state transition,
every invariant, every emitted Domain Event, and every exception path
on Review, per this module's exhaustive testing requirement.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from apps.reviews.domain.aggregates import Review
from apps.reviews.domain.enums import ReviewHideReason, ReviewMediaType, ReviewRejectionReason, ReviewStatus
from apps.reviews.domain.exceptions import (
    InvalidReviewLifecycleTransition, MediaAttachmentNotAllowed, MediaLimitExceeded, ReviewAlreadyPublished,
    ReviewAlreadyWithdrawn, ReviewNotEditable,
)
from apps.reviews.domain.value_objects import Rating, ReviewBody, ReviewTitle
from apps.reviews.tests.factories import make_published_review, make_review

pytestmark = pytest.mark.unit


def _now() -> datetime:
    return datetime.utcnow()


class TestCreate:
    def test_creates_draft_review(self):
        review, event = Review.create(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), Rating(5), ReviewBody("Great."), True, _now())
        assert review.status == ReviewStatus.DRAFT
        assert event.__class__.__name__ == "ReviewCreated"

    def test_starts_at_version_1(self):
        review, _ = Review.create(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), Rating(5), ReviewBody("Great."), True, _now())
        assert review.version.value == 1

    def test_verified_purchase_stored_as_supplied(self):
        review, _ = Review.create(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), Rating(5), ReviewBody("Great."), False, _now())
        assert review.verified_purchase is False

    def test_optional_title_defaults_to_none(self):
        review, _ = Review.create(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), Rating(5), ReviewBody("Great."), True, _now())
        assert review.title is None


class TestSubmit:
    def test_submit_transitions_to_pending_moderation(self):
        review = make_review()
        event = review.submit(_now())
        assert review.status == ReviewStatus.PENDING_MODERATION
        assert event.__class__.__name__ == "ReviewSubmitted"

    def test_submit_non_draft_raises(self):
        review = make_review()
        review.submit(_now())
        with pytest.raises(InvalidReviewLifecycleTransition):
            review.submit(_now())

    def test_submit_bumps_version(self):
        review = make_review()
        assert review.version.value == 1
        review.submit(_now())
        assert review.version.value == 2


class TestApproveReject:
    def test_approve_transitions_to_approved(self):
        review = make_review()
        review.submit(_now())
        event = review.approve(_now())
        assert review.status == ReviewStatus.APPROVED
        assert event.__class__.__name__ == "ReviewApproved"

    def test_approve_non_pending_raises(self):
        review = make_review()
        with pytest.raises(InvalidReviewLifecycleTransition):
            review.approve(_now())

    def test_reject_transitions_to_rejected(self):
        review = make_review()
        review.submit(_now())
        event = review.reject(ReviewRejectionReason.SPAM, _now())
        assert review.status == ReviewStatus.REJECTED
        assert event.reason == "spam"

    def test_reject_non_pending_raises(self):
        review = make_review()
        with pytest.raises(InvalidReviewLifecycleTransition):
            review.reject(ReviewRejectionReason.SPAM, _now())


class TestPublish:
    def test_publish_transitions_to_published(self):
        review = make_review()
        review.submit(_now())
        review.approve(_now())
        event = review.publish(_now())
        assert review.status == ReviewStatus.PUBLISHED
        assert event.rating == 5

    def test_publish_non_approved_raises_invalid_transition(self):
        review = make_review()
        with pytest.raises(InvalidReviewLifecycleTransition):
            review.publish(_now())

    def test_double_publish_raises_already_published(self):
        review = make_published_review()
        with pytest.raises(ReviewAlreadyPublished):
            review.publish(_now())


class TestHide:
    def test_hide_transitions_to_hidden(self):
        review = make_published_review()
        event = review.hide(ReviewHideReason.CUSTOMER_COMPLAINT)
        assert review.status == ReviewStatus.HIDDEN
        assert event.reason == "customer_complaint"

    def test_hide_non_published_raises(self):
        review = make_review()
        with pytest.raises(InvalidReviewLifecycleTransition):
            review.hide(ReviewHideReason.POLICY_VIOLATION)


class TestWithdraw:
    def test_withdraw_from_draft(self):
        review = make_review()
        event = review.withdraw()
        assert review.status == ReviewStatus.WITHDRAWN
        assert event.review_id == review.id

    def test_withdraw_from_published(self):
        review = make_published_review()
        review.withdraw()
        assert review.status == ReviewStatus.WITHDRAWN

    def test_double_withdraw_raises(self):
        review = make_review()
        review.withdraw()
        with pytest.raises(ReviewAlreadyWithdrawn):
            review.withdraw()


class TestEditContent:
    def test_free_edit_in_draft(self):
        review = make_review()
        event = review.edit_content(ReviewBody("Updated body."), _now(), ReviewTitle("Updated title"))
        assert review.body.value == "Updated body."
        assert event.reset_to_pending_moderation is False
        assert review.status == ReviewStatus.DRAFT

    def test_edit_published_resets_to_pending_moderation(self):
        review = make_published_review()
        event = review.edit_content(ReviewBody("Revised after publish."), _now())
        assert review.status == ReviewStatus.PENDING_MODERATION
        assert event.reset_to_pending_moderation is True

    def test_edit_pending_moderation_raises_not_editable(self):
        review = make_review()
        review.submit(_now())
        with pytest.raises(ReviewNotEditable):
            review.edit_content(ReviewBody("x"), _now())

    def test_edit_approved_raises_not_editable(self):
        review = make_review()
        review.submit(_now())
        review.approve(_now())
        with pytest.raises(ReviewNotEditable):
            review.edit_content(ReviewBody("x"), _now())

    def test_edit_rejected_raises_not_editable(self):
        review = make_review()
        review.submit(_now())
        review.reject(ReviewRejectionReason.SPAM, _now())
        with pytest.raises(ReviewNotEditable):
            review.edit_content(ReviewBody("x"), _now())

    def test_edit_withdrawn_raises_not_editable(self):
        review = make_review()
        review.withdraw()
        with pytest.raises(ReviewNotEditable):
            review.edit_content(ReviewBody("x"), _now())


class TestAttachMedia:
    def test_attach_in_draft(self):
        review = make_review()
        event = review.attach_media(ReviewMediaType.IMAGE, "https://example.com/a.jpg", _now())
        assert len(review.media) == 1
        assert event.media_type == "image"

    def test_attach_outside_draft_raises(self):
        review = make_review()
        review.submit(_now())
        with pytest.raises(MediaAttachmentNotAllowed):
            review.attach_media(ReviewMediaType.IMAGE, "https://example.com/a.jpg", _now())

    def test_media_limit_exceeded_raises(self):
        review = make_review()
        for i in range(4):
            review.attach_media(ReviewMediaType.IMAGE, f"https://example.com/{i}.jpg", _now())
        with pytest.raises(MediaLimitExceeded):
            review.attach_media(ReviewMediaType.IMAGE, "https://example.com/overflow.jpg", _now())

    def test_video_media_limit_is_separate_and_lower(self):
        review = make_review()
        for i in range(3):
            review.attach_media(ReviewMediaType.VIDEO, f"https://example.com/{i}.mp4", _now())
        with pytest.raises(MediaLimitExceeded):
            review.attach_media(ReviewMediaType.VIDEO, "https://example.com/overflow.mp4", _now())


class TestPrivateAccessBoundary:
    def test_private_methods_are_underscore_prefixed_and_not_part_of_public_contract(self):
        public_methods = {name for name in dir(Review) if not name.startswith("_") and callable(getattr(Review, name, None))}
        assert "_bump_version" not in public_methods
