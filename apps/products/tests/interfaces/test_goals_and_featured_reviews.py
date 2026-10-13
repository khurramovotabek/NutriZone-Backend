"""Shop by goal (product goals, catalog filter + facet, /products/goals) and the home page's featured reviews."""
from __future__ import annotations

import uuid

import pytest
from django.utils import timezone

from apps.products.infrastructure import models as p
from apps.reviews.infrastructure.models import ReviewModel

pytestmark = pytest.mark.django_db


def _product(name, goals, status="published"):
    prod = p.Product.objects.create(id=uuid.uuid4(), status=status, goals=goals)
    p.ProductTranslation.objects.create(id=uuid.uuid4(), product=prod, locale_code="uz", name=name, slug=f"g-{uuid.uuid4().hex[:8]}")
    p.ProductVariant.objects.create(id=uuid.uuid4(), product=prod, sku=f"G-{uuid.uuid4().hex[:6]}", is_default=True)
    return prod


def test_goal_filter_facet_and_counts(client):
    whey = _product("Whey G", ["muscle"])
    burner = _product("Burner G", ["weight_loss", "endurance"])
    _product("Hidden G", ["muscle"], status="draft")
    goals = {g["code"]: g["count"] for g in client.get("/api/v1/products/goals").json()["data"]}
    assert goals["muscle"] == 1 and goals["weight_loss"] == 1 and goals["health"] == 0
    r = client.get("/api/v1/products/search", {"filter[goal]": "muscle"}).json()
    ids = {x["id"] for x in r["data"]}
    assert str(whey.id) in ids and str(burner.id) not in ids
    assert client.get("/api/v1/products/search", {"filter[goal]": "flying"}).status_code == 422


def test_featured_reviews_only_good_published_reviews_of_live_products(client):
    live, gone = _product("Kreatin R", ["muscle"]), _product("Old R", [], status="draft")
    now = timezone.now()
    def rv(product, rating, body, status="published"):
        return ReviewModel.objects.create(product_id=product.id, customer_id=uuid.uuid4(), rating=rating, body=body, status=status, published_at=now, verified_purchase=True)
    good = rv(live, 5, "Juda sifatli, natijasi ikki haftada ko'rindi")
    rv(live, 2, "Menga umuman yoqmadi, qaytardim")
    rv(live, 5, "zo'r")  # too short to be a testimonial
    rv(gone, 5, "Yaxshi edi lekin endi sotilmaydi")
    rv(live, 5, "Hali moderatsiyada turgan sharh", status="approved")
    data = client.get("/api/v1/reviews/featured").json()["data"]
    assert [x["id"] for x in data["results"]] == [str(good.id)]
    assert data["results"][0]["product"]["name"] == "Kreatin R" and data["count"] == 4
