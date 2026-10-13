from __future__ import annotations

import ast
from datetime import datetime, timedelta

import pytest

import apps.reviews.domain.exceptions as exceptions_module
from apps.reviews.domain import exceptions as exc
from apps.reviews.domain.enums import ReviewStatus
from apps.reviews.domain.services import DEFAULT_MODERATION_SLA, MAX_IMAGE_MEDIA_ITEMS, MAX_VIDEO_MEDIA_ITEMS, ReviewEditPolicy, ReviewEligibilityPolicy, ReviewModerationSLACalculator
from apps.reviews.domain.validators import RatingValidator, ReviewBodyValidator, ReviewTitleValidator
from common.exceptions import DomainException

pytestmark = pytest.mark.unit


class TestReviewEligibilityPolicy:
    def test_verified_purchase_can_submit(self):
        assert ReviewEligibilityPolicy.can_submit(True) is True

    def test_unverified_purchase_cannot_submit(self):
        assert ReviewEligibilityPolicy.can_submit(False) is False


class TestReviewEditPolicy:
    """Hand-traced during Phase 1 (DRAFT/PUBLISHED editable, all else not); now made executable across all 7 status values."""

    @pytest.mark.parametrize("status", [ReviewStatus.DRAFT, ReviewStatus.PUBLISHED])
    def test_editable_statuses(self, status):
        assert ReviewEditPolicy.can_edit(status) is True

    @pytest.mark.parametrize("status", [ReviewStatus.PENDING_MODERATION, ReviewStatus.APPROVED, ReviewStatus.REJECTED, ReviewStatus.HIDDEN, ReviewStatus.WITHDRAWN])
    def test_non_editable_statuses(self, status):
        assert ReviewEditPolicy.can_edit(status) is False

    def test_draft_does_not_require_remoderation(self):
        assert ReviewEditPolicy.requires_remoderation(ReviewStatus.DRAFT) is False

    def test_published_requires_remoderation(self):
        assert ReviewEditPolicy.requires_remoderation(ReviewStatus.PUBLISHED) is True


class TestReviewModerationSLACalculator:
    def test_not_overdue_within_sla(self):
        submitted_at = datetime.utcnow()
        assert ReviewModerationSLACalculator.is_overdue(submitted_at, submitted_at + timedelta(hours=1)) is False

    def test_overdue_past_sla(self):
        submitted_at = datetime.utcnow()
        assert ReviewModerationSLACalculator.is_overdue(submitted_at, submitted_at + DEFAULT_MODERATION_SLA + timedelta(minutes=1)) is True

    def test_exactly_at_sla_boundary_is_overdue(self):
        submitted_at = datetime.utcnow()
        assert ReviewModerationSLACalculator.is_overdue(submitted_at, submitted_at + DEFAULT_MODERATION_SLA) is True

    def test_default_sla_is_48_hours(self):
        assert DEFAULT_MODERATION_SLA == timedelta(hours=48)

    def test_max_image_media_items_is_4(self):
        assert MAX_IMAGE_MEDIA_ITEMS == 4

    def test_max_video_media_items_is_3(self):
        assert MAX_VIDEO_MEDIA_ITEMS == 3


class TestValidators:
    def test_rating_validator(self):
        assert RatingValidator(4).value == 4

    def test_review_title_validator(self):
        assert ReviewTitleValidator("Nice").value == "Nice"

    def test_review_body_validator(self):
        assert ReviewBodyValidator("Solid.").value == "Solid."


@pytest.mark.parametrize(
    "exception_cls",
    [
        exc.InvalidReviewLifecycleTransition, exc.ReviewAlreadyPublished, exc.ReviewAlreadyWithdrawn,
        exc.ReviewNotEditable, exc.MediaAttachmentNotAllowed, exc.MediaLimitExceeded, exc.InvalidRating,
        exc.ReviewContentTooLong,
    ],
)
def test_every_exception_subclasses_domain_exception(exception_cls):
    assert issubclass(exception_cls, DomainException)
    instance = exception_cls("test message")
    assert instance.message == "test message"
    assert instance.code


def test_programmatically_verify_exactly_8_exceptions():
    """AST-parses exceptions.py directly, per this build's established pattern of verifying programmatically rather than trusting a hardcoded count."""
    tree = ast.parse(open(exceptions_module.__file__).read())
    class_names = [n.name for n in tree.body if isinstance(n, ast.ClassDef)]
    assert len(class_names) == 8, f"Expected exactly 8 Reviews domain exceptions, found {len(class_names)}: {class_names}"
