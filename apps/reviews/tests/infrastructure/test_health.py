"""
**Covers all 6 real health checks that actually exist in
`apps/reviews/infrastructure/health.py`, not the 5 this phase's own
prompt expected** -- re-verified fresh in this phase's Step 1 and
documented as a stale-expectation discrepancy in the certification
report, not silently adjusted to match either number without
disclosure.
"""
from __future__ import annotations

import uuid

import pytest
from django.db import connection

from apps.reviews.infrastructure import models as orm
from apps.reviews.infrastructure.health import (
    check_composition_integrity,
    check_orphaned_media,
    check_rating_constraint_integrity,
    check_review_cache,
    check_review_outbox_backlog,
    check_review_repository,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestHealthChecks:
    def test_check_review_repository_healthy(self):
        ok, detail = check_review_repository()
        assert ok is True

    def test_check_review_outbox_backlog_reports_count(self):
        ok, detail = check_review_outbox_backlog()
        assert ok is True
        assert "pending" in detail

    def test_check_rating_constraint_integrity_healthy_by_default(self):
        ok, detail = check_rating_constraint_integrity()
        assert ok is True

    def test_check_orphaned_media_healthy_by_default(self):
        ok, detail = check_orphaned_media()
        assert ok is True

    def test_check_composition_integrity_healthy(self):
        ok, detail = check_composition_integrity()
        assert ok is True

    def test_check_review_cache_round_trips(self):
        ok, detail = check_review_cache()
        assert ok is True

    def test_check_orphaned_media_flags_seeded_orphan(self):
        """Seeds a deliberately orphaned media row (bypassing the ORM's normal review relationship) and verifies the check actually catches it, not just runs without error. Uses raw SQL to bypass Django's own FK enforcement at the ORM layer, matching how a real data-integrity drift (e.g. a bad migration) would occur. The FK is DEFERRABLE INITIALLY DEFERRED (confirmed directly against the live schema), so the UPDATE itself succeeds within this test's own transaction -- the row is genuinely orphaned, not merely attempted. Restores a valid review_id before the test ends so Django's own teardown-time constraint re-check (SET CONSTRAINTS ALL IMMEDIATE, run before the transaction rollback) doesn't hit this deliberately-left corruption."""
        row = orm.ReviewModel.objects.create(product_id=uuid.uuid4(), customer_id=uuid.uuid4(), rating=5, body="x")
        media = orm.ReviewMediaModel.objects.create(review=row, media_type="image", url="https://example.com/a.jpg", uploaded_at="2026-01-01T00:00:00Z")
        with connection.cursor() as cursor:
            cursor.execute("UPDATE reviews_review_media SET review_id = %s WHERE id = %s", [str(uuid.uuid4()), str(media.id)])
        ok, detail = check_orphaned_media()
        assert ok is False

        with connection.cursor() as cursor:
            cursor.execute("UPDATE reviews_review_media SET review_id = %s WHERE id = %s", [str(row.id), str(media.id)])
