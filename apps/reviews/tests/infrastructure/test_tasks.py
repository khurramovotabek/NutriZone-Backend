from __future__ import annotations

import pytest

from apps.reviews.infrastructure.tasks import flag_overdue_moderation_reviews, rebuild_review_statistics, relay_outbox_events
from apps.reviews.infrastructure.repositories import DjangoReviewRepository
from apps.reviews.tests.factories import make_review

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestCeleryTasks:
    def test_flag_overdue_moderation_reviews_runs_without_error(self):
        assert isinstance(flag_overdue_moderation_reviews(), int)

    def test_flag_overdue_moderation_reviews_never_mutates_a_review(self):
        """Verifies the disclosed read-only design documented in Phase 2: this task must never change a Review's status, only report on it."""
        review = make_review()
        review.submit(review.created_at)
        repo = DjangoReviewRepository()
        repo.save(review)

        flag_overdue_moderation_reviews()

        fetched = repo.get_by_id(review.id)
        assert fetched.status.value == "pending_moderation"

    def test_rebuild_review_statistics_runs_without_error(self):
        assert rebuild_review_statistics() == "ok"

    def test_relay_outbox_events_runs_without_error(self):
        result = relay_outbox_events()
        assert isinstance(result, dict)
