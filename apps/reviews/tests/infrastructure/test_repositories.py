"""
Repository integration tests -- require a real PostgreSQL database.
Matches every prior module's `tests/infrastructure/test_repositories.py`
pattern. Includes explicit database-constraint verification, not just
round-trip tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from django.db import IntegrityError

from apps.reviews.domain.enums import ReviewMediaType
from apps.reviews.infrastructure import models as orm
from apps.reviews.infrastructure.repositories import DjangoReviewRepository
from apps.reviews.tests.factories import make_published_review, make_review

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoReviewRepository:
    def test_save_then_get_by_id_round_trips(self):
        repo = DjangoReviewRepository()
        review = make_review()
        repo.save(review)

        fetched = repo.get_by_id(review.id)
        assert fetched is not None
        assert fetched.rating.value == review.rating.value
        assert fetched.body.value == review.body.value

    def test_title_none_round_trips_correctly(self):
        repo = DjangoReviewRepository()
        review = make_review(title=None)
        repo.save(review)
        assert repo.get_by_id(review.id).title is None

    def test_get_by_id_missing_returns_none(self):
        repo = DjangoReviewRepository()
        assert repo.get_by_id(uuid.uuid4()) is None

    def test_media_round_trips(self):
        repo = DjangoReviewRepository()
        review = make_review()
        review.attach_media(ReviewMediaType.IMAGE, "https://example.com/a.jpg", datetime.utcnow())
        repo.save(review)

        fetched = repo.get_by_id(review.id)
        assert len(fetched.media) == 1
        entry = next(iter(fetched.media.values()))
        assert entry.url == "https://example.com/a.jpg"

    def test_status_and_lifecycle_timestamps_round_trip(self):
        repo = DjangoReviewRepository()
        review = make_published_review()
        repo.save(review)

        fetched = repo.get_by_id(review.id)
        assert fetched.status.value == "published"
        assert fetched.submitted_at is not None
        assert fetched.moderated_at is not None
        assert fetched.published_at is not None

    def test_database_level_rating_check_constraint(self):
        with pytest.raises(IntegrityError):
            orm.ReviewModel.objects.create(product_id=uuid.uuid4(), customer_id=uuid.uuid4(), rating=6, body="x")

    def test_list_for_product(self):
        repo = DjangoReviewRepository()
        review = make_review()
        repo.save(review)
        results, total = repo.list_for_product(review.product_id, status=None, page=1, page_size=20)
        assert total == 1

    def test_list_for_product_filters_by_status(self):
        repo = DjangoReviewRepository()
        review = make_published_review()
        repo.save(review)
        results, total = repo.list_for_product(review.product_id, status="published", page=1, page_size=20)
        assert total == 1
        results, total = repo.list_for_product(review.product_id, status="draft", page=1, page_size=20)
        assert total == 0

    def test_list_for_customer(self):
        repo = DjangoReviewRepository()
        review = make_review()
        repo.save(review)
        results, total = repo.list_for_customer(review.customer_id, page=1, page_size=20)
        assert total == 1

    def test_list_for_admin(self):
        repo = DjangoReviewRepository()
        repo.save(make_review())
        results, total = repo.list_for_admin(status=None, page=1, page_size=20)
        assert total >= 1
