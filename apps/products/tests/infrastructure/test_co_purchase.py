"""'Ko'pincha birga olinadi': related products from real baskets, the product page fallback order and the cart cross-sell."""
from __future__ import annotations

import uuid

import pytest
from django.core.cache import cache
from django.test import Client

from apps.products.infrastructure import co_purchase
from apps.products.infrastructure.models import Product, ProductTranslation

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_table():
    cache.delete(co_purchase.CACHE_KEY)
    yield
    cache.delete(co_purchase.CACHE_KEY)


def _product(name: str, category=None) -> Product:
    p = Product.objects.create(id=uuid.uuid4(), status="published", category_id=category)
    ProductTranslation.objects.create(id=uuid.uuid4(), product=p, locale_code="uz", name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:6]}")
    return p


def _baskets(monkeypatch, *baskets):
    monkeypatch.setattr(co_purchase, "_baskets", lambda: [frozenset(p.id for p in b) for b in baskets])


def test_a_real_pairing_beats_a_best_seller_that_is_in_every_basket(monkeypatch):
    whey, shaker, bestseller, vitamin = (_product(n) for n in ("Whey", "Shaker", "Bestseller", "Vitamin"))
    _baskets(monkeypatch, [whey, shaker, bestseller], [whey, shaker], [whey, bestseller], [bestseller, vitamin], [bestseller, vitamin], [bestseller])

    assert co_purchase.related(whey.id)[:2] == [shaker.id, bestseller.id]
    assert co_purchase.for_basket([whey.id, shaker.id]) == [bestseller.id]  # nothing already in the cart


def test_product_page_without_a_staff_pick_shows_bought_together_then_category(monkeypatch):
    from apps.products.infrastructure.selectors import RecommendationSelector
    from apps.products.tests.interfaces.test_recommendations_integration import _real_category

    category_id = _real_category()
    main, sibling = _product("Main", category_id), _product("Sibling", category_id)
    pair = _product("Pair")  # another category, but bought together with Main
    _baskets(monkeypatch, [main, pair], [main, pair])

    ids = [c["id"] for c in RecommendationSelector().for_product(main.id)]
    assert ids == [str(pair.id), str(sibling.id)]


def test_cart_cross_sell_endpoint(monkeypatch):
    whey, shaker, creatine = _product("Whey"), _product("Shaker"), _product("Creatine")
    _baskets(monkeypatch, [whey, shaker], [whey, shaker, creatine])

    body = Client().get(f"/api/v1/products/recommendations/for-cart?ids={whey.id},not-a-uuid").json()
    assert [c["id"] for c in body["data"]] == [str(shaker.id), str(creatine.id)]
    assert Client().get("/api/v1/products/recommendations/for-cart").json()["data"] == []


def test_cart_endpoint_accepts_variant_ids(monkeypatch):
    from apps.products.infrastructure.models import ProductVariant

    whey, shaker = _product("Whey"), _product("Shaker")
    variant = ProductVariant.objects.create(id=uuid.uuid4(), product=whey, sku=f"V-{uuid.uuid4().hex[:6]}", is_default=True)
    _baskets(monkeypatch, [whey, shaker])

    body = Client().get(f"/api/v1/products/recommendations/for-cart?ids={variant.id}").json()
    assert [c["id"] for c in body["data"]] == [str(shaker.id)]
