"""
Real, live-verified regression test for Phase Homepage-Rebuild: no
product-level rating aggregation previously existed anywhere in the
project (confirmed via direct inspection -- Reviews' own
ReviewStatisticsSelector only had counts_by_status(), an admin-only,
status-grouped count). Every scenario here was proven live before
being formalized.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import Client

from apps.products.infrastructure import models as p_models
from apps.reviews.infrastructure import models as r_models

pytestmark = pytest.mark.django_db


def _make_product(name: str = "Rated Product") -> tuple[p_models.Product, str]:
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    slug = f"rp-{uuid.uuid4().hex[:8]}"
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name=name, slug=slug)
    return product, slug


class TestProductRatingAggregation:
    def test_average_and_count_reflect_only_published_reviews(self):
        product, slug = _make_product()
        r_models.ReviewModel.objects.create(id=uuid.uuid4(), product_id=product.id, customer_id=uuid.uuid4(), rating=5, body="Great", status="published")
        r_models.ReviewModel.objects.create(id=uuid.uuid4(), product_id=product.id, customer_id=uuid.uuid4(), rating=3, body="OK", status="published")
        r_models.ReviewModel.objects.create(id=uuid.uuid4(), product_id=product.id, customer_id=uuid.uuid4(), rating=1, body="Not published", status="draft")

        client = Client()
        response = client.get(f"/api/v1/products/{slug}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["rating_average"] == 4.0
        assert data["rating_count"] == 2

    def test_product_with_no_reviews_has_null_average_and_zero_count(self):
        product, slug = _make_product(name="Unreviewed Product")

        client = Client()
        response = client.get(f"/api/v1/products/{slug}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["rating_average"] is None
        assert data["rating_count"] == 0

    def test_product_list_exposes_the_same_rating_for_the_same_product(self):
        product, slug = _make_product(name="List Rating Product")
        r_models.ReviewModel.objects.create(id=uuid.uuid4(), product_id=product.id, customer_id=uuid.uuid4(), rating=4, body="Good", status="published")

        client = Client()
        response = client.get("/api/v1/products?page_size=200")
        assert response.status_code == 200
        matching = next((p for p in response.json()["data"] if p["id"] == str(product.id)), None)
        assert matching is not None
        assert matching["rating_average"] == 4.0
        assert matching["rating_count"] == 1
