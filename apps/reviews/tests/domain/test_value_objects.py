from __future__ import annotations

import pytest

from apps.reviews.domain.exceptions import InvalidRating, ReviewContentTooLong
from apps.reviews.domain.value_objects import MAX_BODY_LENGTH, MAX_TITLE_LENGTH, Rating, ReviewBody, ReviewTitle, ReviewVersion
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


class TestRating:
    """Explicit boundary: 1 is valid, 5 is valid, 0 and 6 both raise."""

    def test_minimum_valid(self):
        assert Rating(1).value == 1

    def test_maximum_valid(self):
        assert Rating(5).value == 5

    def test_below_minimum_raises_invalid_rating(self):
        with pytest.raises(InvalidRating):
            Rating(0)

    def test_above_maximum_raises_invalid_rating(self):
        with pytest.raises(InvalidRating):
            Rating(6)

    def test_equality(self):
        assert Rating(3) == Rating(3)

    def test_hashable(self):
        {Rating(3)}

    def test_immutability(self):
        rating = Rating(3)
        with pytest.raises(Exception):
            rating.value = 5  # type: ignore[misc]


class TestReviewTitle:
    def test_valid_construction(self):
        assert ReviewTitle("Great product").value == "Great product"

    def test_rejects_empty_string(self):
        with pytest.raises(ValidationFailed):
            ReviewTitle("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValidationFailed):
            ReviewTitle("   ")

    def test_rejects_too_long_with_specific_exception(self):
        with pytest.raises(ReviewContentTooLong):
            ReviewTitle("x" * (MAX_TITLE_LENGTH + 1))

    def test_exactly_max_length_allowed(self):
        ReviewTitle("x" * MAX_TITLE_LENGTH)


class TestReviewBody:
    def test_valid_construction(self):
        assert ReviewBody("Solid product overall.").value == "Solid product overall."

    def test_rejects_empty_string(self):
        with pytest.raises(ValidationFailed):
            ReviewBody("")

    def test_rejects_too_long_with_specific_exception(self):
        with pytest.raises(ReviewContentTooLong):
            ReviewBody("x" * (MAX_BODY_LENGTH + 1))

    def test_exactly_max_length_allowed(self):
        ReviewBody("x" * MAX_BODY_LENGTH)


class TestReviewVersion:
    def test_valid_construction(self):
        assert ReviewVersion(1).value == 1

    def test_rejects_zero(self):
        with pytest.raises(ValidationFailed):
            ReviewVersion(0)

    def test_next_increments(self):
        assert ReviewVersion(1).next().value == 2

    def test_next_does_not_mutate_original(self):
        original = ReviewVersion(1)
        original.next()
        assert original.value == 1
