"""
Phase 03A's Reviews IDOR regression suite. Proves a real vulnerability
found and fixed this phase across 2 views: ReviewDetailView and
CustomerReviewListView -- both trusted a URL-supplied identifier with
zero ownership check, despite ViewOwnReviews' own docstring explicitly
distinguishing "own reviews" (private) from the separate, genuinely
public product-review-list endpoint (not affected -- confirmed
unchanged). Also caught two existing tests that were unknowingly
passing by exploiting this exact bug (see test_api_integration.py's
own corrected fixtures).
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.reviews.infrastructure.repositories import DjangoReviewRepository
from apps.reviews.tests.factories import make_review
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class _CustomerOnlyResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return permission_code == "reviews.review.view_own"


def _client_as(monkeypatch, user_id) -> APIClient:
    monkeypatch.setattr(HasPermissionCode, "resolver", _CustomerOnlyResolver())
    fake_user = SimpleNamespace(id=user_id, is_authenticated=True, store_ids=set())
    monkeypatch.setattr(
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
        lambda self, request: (fake_user, None),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
    return client


class TestReviewDetailIDOR:
    def test_customer_a_cannot_view_customer_b_review(self, monkeypatch):
        customer_b = uuid.uuid4()
        review = make_review(customer_id=customer_b)
        DjangoReviewRepository().save(review)
        client = _client_as(monkeypatch, uuid.uuid4())
        response = client.get(f"/api/v1/reviews/{review.id}")
        assert response.status_code == 403

    def test_customer_can_view_own_review(self, monkeypatch):
        customer_b = uuid.uuid4()
        review = make_review(customer_id=customer_b)
        DjangoReviewRepository().save(review)
        client = _client_as(monkeypatch, customer_b)
        response = client.get(f"/api/v1/reviews/{review.id}")
        assert response.status_code == 200


class TestCustomerReviewListIDOR:
    def test_customer_a_cannot_list_customer_b_reviews(self, monkeypatch):
        customer_b = uuid.uuid4()
        client = _client_as(monkeypatch, uuid.uuid4())
        response = client.get(f"/api/v1/reviews/customers/{customer_b}")
        assert response.status_code == 403

    def test_customer_can_list_own_reviews(self, monkeypatch):
        customer_b = uuid.uuid4()
        client = _client_as(monkeypatch, customer_b)
        response = client.get(f"/api/v1/reviews/customers/{customer_b}")
        assert response.status_code == 200


class TestPublicProductReviewsUnaffected:
    def test_product_review_list_remains_public_no_ownership_required(self, monkeypatch):
        """Confirms the fix was scoped correctly -- the genuinely public product-review-list endpoint (a different view, ViewOwnReviews's own docstring explicitly excludes it) was not accidentally locked down."""
        review = make_review()
        DjangoReviewRepository().save(review)
        client = _client_as(monkeypatch, uuid.uuid4())  # a customer with no relation to this review at all
        response = client.get(f"/api/v1/reviews/products/{review.product_id}")
        assert response.status_code == 200
