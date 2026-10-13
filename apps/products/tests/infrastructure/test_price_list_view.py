"""
Price List dashboard page's Stock column -- backed by the WMS stock
(stores.StoreProductStock, on hand − reserved), the same numbers the
warehouse, POS and storefront use. A variant with no stock row at all is
genuinely not stock-tracked ("Not tracked", never a fabricated 0); one
that IS tracked sums its sellable units across every location.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.models import User
from django.test import Client

from apps.products.infrastructure import models as p_models

pytestmark = pytest.mark.django_db


def _staff_client() -> Client:
    admin_user = User.objects.create_superuser(username=f"admin_{uuid.uuid4().hex[:6]}", password="test-pass-12345")
    client = Client()
    client.force_login(admin_user)
    return client


def _make_variant(product_name: str) -> p_models.ProductVariant:
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name=product_name, slug=f"{product_name.lower()}-{uuid.uuid4().hex[:6]}")
    return p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)


class TestPriceListViewStockColumn:
    def test_stock_sums_available_quantity_across_warehouses(self):
        from apps.products.tests.stock_helpers import location, put_stock

        variant = _make_variant("Tracked Stock Product")
        put_stock(variant.id, 7, store=location("WH", kind="warehouse"))
        put_stock(variant.id, 5)

        response = _staff_client().get("/django-admin/products/price-list/", {"q": variant.sku})

        assert response.status_code == 200
        body = response.content.decode()
        assert '<span class="nz-stock-value">12</span>' in body

    def test_untracked_variant_shows_not_tracked_never_a_fabricated_zero(self):
        variant = _make_variant("Untracked Product")

        response = _staff_client().get("/django-admin/products/price-list/", {"q": variant.sku})

        assert response.status_code == 200
        body = response.content.decode()
        assert "nz-stock-untracked" in body
        assert '<span class="nz-stock-value">0</span>' not in body

    def test_tracked_but_empty_variant_shows_a_real_out_of_stock_badge(self):
        from apps.products.tests.stock_helpers import put_stock

        variant = _make_variant("Zero Stock Product")
        put_stock(variant.id, 0)

        response = _staff_client().get("/django-admin/products/price-list/", {"q": variant.sku})

        assert response.status_code == 200
        body = response.content.decode()
        assert "nz-stock-out" in body


class TestPriceListViewGroupedByProduct:
    """Real, product-required simplification: this page's own row unit is a Product now, not a ProductVariant -- a Product with several variants shows exactly one row (its own real default variant's price), with a real "xN" count disclosing that other variants exist, never a fabricated grouping across separate Product records (that stays explicitly banned)."""

    def _make_product_with_two_variants(self, name: str):
        from apps.pricing.infrastructure.models import PriceListEntryModel, PriceListModel

        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name=name, slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}")
        default_variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", is_default=True)
        other_variant = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}")

        price_list = PriceListModel.objects.create(id=uuid.uuid4(), code=f"pl-{uuid.uuid4().hex[:6]}", name="Test", currency="UZS", status="active")
        PriceListEntryModel.objects.create(id=uuid.uuid4(), price_list=price_list, product_variant_id=default_variant.id, base_price_amount="500000")
        PriceListEntryModel.objects.create(id=uuid.uuid4(), price_list=price_list, product_variant_id=other_variant.id, base_price_amount="300000")
        return product, default_variant, other_variant

    def test_a_product_with_two_variants_renders_exactly_one_row(self):
        product, default_variant, _other = self._make_product_with_two_variants("Two Variant Product")

        response = _staff_client().get("/django-admin/products/price-list/", {"q": "Two Variant Product"})

        assert response.status_code == 200
        body = response.content.decode()
        assert body.count('data-variant-id="') == 1
        assert f'data-variant-id="{default_variant.id}"' in body

    def test_the_row_shows_the_default_variants_price_not_the_other_variants(self):
        product, default_variant, other_variant = self._make_product_with_two_variants("Default Price Product")

        response = _staff_client().get("/django-admin/products/price-list/", {"q": "Default Price Product"})

        body = response.content.decode()
        # the product row carries the default variant's price; the other variant is priced in its own expandable sub-row
        assert f'data-variant-id="{default_variant.id}" data-price="500000.00"' in body
        assert f'data-sub-variant-id="{other_variant.id}"' in body
        main_row = body.split(f'data-variant-id="{default_variant.id}"')[1].split("wx-pl-variants")[0]
        assert 'value="500000"' in main_row and 'value="300000"' not in main_row

    def test_a_product_with_more_than_one_variant_shows_a_real_variant_count(self):
        product, _default, _other = self._make_product_with_two_variants("Variant Count Product")

        response = _staff_client().get("/django-admin/products/price-list/", {"q": "Variant Count Product"})

        body = response.content.decode()
        assert "&times;2" in body

    def test_a_product_with_exactly_one_variant_shows_no_variant_count_badge(self):
        variant = _make_variant("Single Variant Product")

        response = _staff_client().get("/django-admin/products/price-list/", {"q": variant.sku})

        body = response.content.decode()
        assert '<span class="nz-badge nz-badge-neutral nz-price-list-variant-count"' not in body

    def test_a_product_with_no_variants_at_all_is_never_listed(self):
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="draft")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name="No Variant Product", slug=f"no-variant-{uuid.uuid4().hex[:6]}")

        response = _staff_client().get("/django-admin/products/price-list/", {"q": "No Variant Product"})

        body = response.content.decode()
        assert 'data-variant-id="' not in body
        assert "No products found" in body


class TestPricingUpgrade:
    def test_add_product_page_lets_you_price_the_new_variants(self):
        body = _staff_client().get("/django-admin/products/product/add/").content.decode()
        for field in ("price", "base_cost_price", "old_price"):
            assert f'name="variants-__prefix__-{field}"' in body
        assert "pricing-group" not in body.lower() or "variants-__prefix__-price" in body

    def test_kpis_missing_filter_and_history(self):
        from apps.pricing.infrastructure.models import PriceHistoryEntryModel, PriceListModel

        unpriced = _make_variant("Unpriced Thing")
        client = _staff_client()
        body = client.get("/django-admin/products/price-list/", {"missing": "1"}).content.decode()
        assert f'data-variant-id="{unpriced.id}"' in body and "is-unpriced" in body
        price_list = PriceListModel.objects.create(id=uuid.uuid4(), code=f"PL-{uuid.uuid4().hex[:6].upper()}", name="T", currency="UZS", status="active")
        PriceHistoryEntryModel.objects.create(price_list=price_list, product_variant_id=unpriced.id, price_type="base", new_amount="99000", reason="manual", changed_at="2026-10-01T10:00:00Z")
        data = client.get(f"/django-admin/products/price-list/api/history/{unpriced.id}").json()["data"]
        assert data and data[0]["new"] == "99000.00"


class TestProductListQuickPriceEditor:
    """The product list's price cell opens every variant of the product; saving goes through the price-list API."""

    def test_variants_endpoint_and_save_round_trip(self):
        import json

        client = _staff_client()
        variant = _make_variant("Quick Price Whey")
        second = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=variant.product, sku=f"SKU-{uuid.uuid4().hex[:6]}")

        data = client.get(f"/django-admin/products/price-list/api/product/{variant.product_id}").json()["data"]
        assert data["name"] == "Quick Price Whey" and [v["id"] for v in data["variants"]] == [str(variant.id), str(second.id)]
        assert data["variants"][0]["price"] is None and data["variants"][0]["stock"] == 0

        r = client.post(f"/django-admin/products/price-list/api/save/{second.id}", json.dumps({"price": 245000, "base_price": 180000, "old_price": 270000}), content_type="application/json")
        assert r.json()["success"]
        again = client.get(f"/django-admin/products/price-list/api/product/{variant.product_id}").json()["data"]["variants"][1]
        assert (again["price"], again["cost"], again["old_price"]) == ("245000.00", "180000.00", "270000.00")
        bad = client.post(f"/django-admin/products/price-list/api/save/{second.id}", json.dumps({"price": 300000, "old_price": 200000}), content_type="application/json")
        assert bad.status_code == 422  # old price must be above the price

        page = client.get("/django-admin/products/product/").content.decode()
        assert 'data-nzq="' in page and "nutrizone-price-quick.js" in page

    def test_unknown_product_is_404_and_staff_only(self):
        assert _staff_client().get(f"/django-admin/products/price-list/api/product/{uuid.uuid4()}").status_code == 404
        assert Client().get(f"/django-admin/products/price-list/api/product/{uuid.uuid4()}").status_code == 302
