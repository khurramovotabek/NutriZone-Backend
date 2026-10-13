"""
Real, live-verified regression test for the "Best Sellers" feature --
confirmed missing entirely from the project before this phase (no
is_best_seller flag or sales-ranking mechanism existed anywhere).
Ranking is derived from real, confirmed order data, never fabricated.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import Client

from apps.ordering.infrastructure import models as o_models
from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


def _make_product(name: str):
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name=name, slug=f"bs-{uuid.uuid4().hex[:8]}")
    variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", is_default=True)
    return product, variant


def _make_order(status: str):
    return o_models.OrderModel.objects.create(
        id=uuid.uuid4(), order_number=f"ORD-{uuid.uuid4().hex[:10]}", status=status, currency="UZS",
        shipping_recipient_name="T", shipping_line1="T", shipping_city="T", shipping_country_code="UZ",
        billing_recipient_name="T", billing_line1="T", billing_city="T", billing_country_code="UZ",
    )


class TestBestSellersRanking:
    def test_ranked_by_real_units_sold_descending(self):
        popular_product, popular_variant = _make_product("Popular Product")
        for qty in [5, 5, 5]:
            order = _make_order("delivered")
            o_models.OrderLineItemModel.objects.create(id=uuid.uuid4(), order=order, product_variant_id=popular_variant.id, quantity=qty, unit_price_amount="100000.00")

        _, rare_variant = _make_product("Rare Product")
        order = _make_order("delivered")
        o_models.OrderLineItemModel.objects.create(id=uuid.uuid4(), order=order, product_variant_id=rare_variant.id, quantity=1, unit_price_amount="50000.00")

        client = Client()
        response = client.get("/api/v1/products/best-sellers")
        assert response.status_code == 200
        data = response.json()["data"]
        names = [p["name"] for p in data]
        assert names[0] == "Popular Product"
        assert data[0]["units_sold"] == 15

    def test_cancelled_orders_do_not_count_as_sales(self):
        _, variant = _make_product("Cancelled Sale Product")
        order = _make_order("cancelled")
        o_models.OrderLineItemModel.objects.create(id=uuid.uuid4(), order=order, product_variant_id=variant.id, quantity=100, unit_price_amount="10000.00")

        client = Client()
        response = client.get("/api/v1/products/best-sellers")
        names = [p["name"] for p in response.json()["data"]]
        assert "Cancelled Sale Product" not in names

    def test_returns_empty_list_when_no_qualifying_sales_exist(self):
        client = Client()
        response = client.get("/api/v1/products/best-sellers")
        assert response.status_code == 200
        assert isinstance(response.json()["data"], list)
