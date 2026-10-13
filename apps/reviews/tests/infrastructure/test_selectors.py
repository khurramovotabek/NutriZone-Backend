from __future__ import annotations

from datetime import datetime

import pytest

from apps.reviews.domain.enums import ReviewMediaType
from apps.reviews.infrastructure.repositories import DjangoReviewRepository
from apps.reviews.infrastructure.selectors import ReviewMediaSelector, ReviewSelector, ReviewStatisticsSelector
from apps.reviews.tests.factories import make_published_review, make_review

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestReviewSelector:
    def test_list_for_product(self):
        review = make_review()
        DjangoReviewRepository().save(review)
        results, total = ReviewSelector().list_for_product(review.product_id, status=None, page=1, page_size=20)
        assert total == 1

    def test_list_for_product_filters_by_status(self):
        review = make_published_review()
        DjangoReviewRepository().save(review)
        results, total = ReviewSelector().list_for_product(review.product_id, status="published", page=1, page_size=20)
        assert total == 1
        results, total = ReviewSelector().list_for_product(review.product_id, status="rejected", page=1, page_size=20)
        assert total == 0

    def test_list_for_customer(self):
        review = make_review()
        DjangoReviewRepository().save(review)
        results, total = ReviewSelector().list_for_customer(review.customer_id, page=1, page_size=20)
        assert total == 1
        assert results[0]["id"] == str(review.id)


class TestReviewMediaSelector:
    def test_list_for_review(self):
        review = make_review()
        review.attach_media(ReviewMediaType.IMAGE, "https://example.com/a.jpg", datetime.utcnow())
        DjangoReviewRepository().save(review)
        items = ReviewMediaSelector().list_for_review(review.id)
        assert len(items) == 1
        assert items[0]["url"] == "https://example.com/a.jpg"

    def test_list_for_review_with_no_media(self):
        review = make_review()
        DjangoReviewRepository().save(review)
        assert ReviewMediaSelector().list_for_review(review.id) == []


class TestReviewStatisticsSelector:
    def test_counts_by_status(self):
        DjangoReviewRepository().save(make_review())
        counts = ReviewStatisticsSelector().counts_by_status()
        assert counts.get("draft", 0) >= 1
