"""
Real, live-verified regression test for the genuinely public
product-reviews read path. `ProductReviewListView` claims in its own
docstring to be a public read ("any authenticated user may view a
product's reviews; no ownership check applies") but is actually gated
by `ViewOwnReviews`, which fails closed for an anonymous visitor --
confirmed directly against that permission class before this endpoint
was added. `PublicProductReviewListView` is the real fix: AllowAny,
PUBLISHED-only (forced, never a client-supplied filter).
"""
from __future__ import annotations

import uuid

import pytest
from django.test import Client

from apps.identity.infrastructure import models as identity_orm
from apps.reviews.infrastructure.repositories import DjangoReviewRepository
from apps.reviews.tests.factories import make_published_review, make_review

pytestmark = pytest.mark.django_db


class TestPublicProductReviews:
    def test_anonymous_visitor_can_read_published_reviews_without_auth(self):
        product_id = uuid.uuid4()
        customer = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", full_name="Alisher Karimov")
        review = make_published_review(product_id=product_id, customer_id=customer.id)
        DjangoReviewRepository().save(review)

        client = Client()
        response = client.get(f"/api/v1/reviews/products/{product_id}/public")
        assert response.status_code == 200
        body = response.json()
        assert body["data"][0]["id"] == str(review.id)
        # Full name never leaked -- first name + last initial only.
        assert body["data"][0]["author_name"] == "Alisher K."
        assert body["data"][0]["rating"] == 5
        assert "created_at" in body["data"][0]
        assert body["pagination"]["total_count"] == 1

    def test_draft_and_pending_reviews_are_never_shown_publicly(self):
        product_id = uuid.uuid4()
        draft = make_review(product_id=product_id)
        DjangoReviewRepository().save(draft)

        pending = make_review(product_id=product_id)
        from datetime import datetime

        pending.submit(datetime.utcnow())
        DjangoReviewRepository().save(pending)

        client = Client()
        response = client.get(f"/api/v1/reviews/products/{product_id}/public")
        assert response.status_code == 200
        body = response.json()
        assert body["data"] == []
        assert body["pagination"]["total_count"] == 0

    def test_reviewer_with_no_stored_name_gets_a_generic_label_not_a_blank(self):
        product_id = uuid.uuid4()
        customer = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", full_name="")
        review = make_published_review(product_id=product_id, customer_id=customer.id)
        DjangoReviewRepository().save(review)

        client = Client()
        response = client.get(f"/api/v1/reviews/products/{product_id}/public")
        assert response.status_code == 200
        assert response.json()["data"][0]["author_name"] == "NutriZone customer"
