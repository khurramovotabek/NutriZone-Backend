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

    def test_a_product_with_two_variants_is_one_header_and_one_editable_row_per_variant(self):
        product, default_variant, other_variant = self._make_product_with_two_variants("Two Variant Product")

        response = _staff_client().get("/django-admin/products/price-list/", {"q": "Two Variant Product"})

        assert response.status_code == 200
        body = response.content.decode()
        assert body.count("data-product-head") == 1
        assert 'data-variant-id="' not in body  # the header carries no price inputs of its own
        assert body.count('data-sub-variant-id="') == 2
        assert f'data-sub-variant-id="{default_variant.id}"' in body and f'data-sub-variant-id="{other_variant.id}"' in body
        assert f'data-open-editor="{product.id}"' in body  # the product name opens the variant editor

    def test_each_variant_row_carries_its_own_price_and_the_header_the_range(self):
        product, default_variant, other_variant = self._make_product_with_two_variants("Default Price Product")

        response = _staff_client().get("/django-admin/products/price-list/", {"q": "Default Price Product"})

        body = response.content.decode()
        # one variant row runs up to its action links (the page's script, further down, also mentions "wx-pl-main")
        default_row = body.split(f'data-sub-variant-id="{default_variant.id}"')[1].split('class="wx-row-actions"')[0]
        other_row = body.split(f'data-sub-variant-id="{other_variant.id}"')[1].split('class="wx-row-actions"')[0]
        assert 'value="500000"' in default_row and 'value="300000"' not in default_row
        assert 'value="300000"' in other_row
        assert "wx-pl-main" in default_row and "wx-pl-main" not in other_row
        assert "300 000 – 500 000" in body

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


class TestPriceListBulk:
    """Bulk price changes (a size group, a selection): every variant goes through SetPrice; the rules per operation."""

    def _priced(self, name, prices):
        from decimal import Decimal

        from apps.pricing.infrastructure import composition as pc
        from apps.products.infrastructure.admin import _get_or_create_default_price_list

        pl = _get_or_create_default_price_list()
        product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
        p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="en", name=name, slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}")
        variants = []
        for i, (price, old) in enumerate(prices):
            v = p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"BLK-{uuid.uuid4().hex[:6]}", is_default=i == 0, weight_value=Decimal("2.27"), weight_unit="kg")
            if price is not None:
                pc.build_set_price().execute(price_list_id=pl.id, product_variant_id=v.id, base_amount=Decimal(price), currency=pl.currency, compare_at_amount=Decimal(old) if old else None)
            variants.append(v)
        return variants

    def _entry(self, v):
        from apps.pricing.infrastructure.models import PriceListEntryModel

        return PriceListEntryModel.objects.filter(product_variant_id=v.id).first()

    def _post(self, client, ids, op, value=None):
        import json

        return client.post("/django-admin/products/price-list/api/bulk", json.dumps({"variant_ids": [str(v.id) for v in ids], "op": op, "value": value}), content_type="application/json")

    def test_set_prices_every_variant_and_records_history(self):
        from apps.pricing.infrastructure.models import PriceHistoryEntryModel

        a, b, c = self._priced("Bulk Set Whey", [(1000000, None), (1100000, 1300000), (None, None)])
        response = self._post(_staff_client(), [a, b, c], "set", 1250000)

        assert response.status_code == 200 and len(response.json()["data"]["updated"]) == 3
        assert [int(self._entry(v).base_price_amount) for v in (a, b, c)] == [1250000] * 3
        assert int(self._entry(b).compare_at_price_amount) == 1300000  # still above the new price -> kept
        assert PriceHistoryEntryModel.objects.filter(product_variant_id=c.id).exists()

    def test_pct_rounds_to_thousands_and_skips_unpriced(self):
        a, b = self._priced("Bulk Pct Whey", [(333000, None), (None, None)])
        data = self._post(_staff_client(), [a, b], "pct", 10).json()["data"]

        assert int(self._entry(a).base_price_amount) == 366000
        assert data["skipped"] == [{"id": str(b.id), "reason": "no_price"}]

    def test_discount_moves_price_to_old_price_and_clear_removes_it(self):
        (a,) = self._priced("Bulk Discount Whey", [(1000000, None)])
        client = _staff_client()
        self._post(client, [a], "discount", 15)
        e = self._entry(a)
        assert (int(e.base_price_amount), int(e.compare_at_price_amount)) == (850000, 1000000)

        self._post(client, [a], "discount", 20)  # a second discount is taken from the regular (old) price, not stacked
        e = self._entry(a)
        assert (int(e.base_price_amount), int(e.compare_at_price_amount)) == (800000, 1000000)

        self._post(client, [a], "clear_discount")
        e = self._entry(a)
        assert (int(e.base_price_amount), e.compare_at_price_amount) == (800000, None)

    def test_invalid_values_are_rejected(self):
        (a,) = self._priced("Bulk Invalid Whey", [(1000000, None)])
        client = _staff_client()
        assert self._post(client, [a], "discount", 100).status_code == 422
        assert self._post(client, [a], "set", 0).status_code == 422
        assert self._post(client, [a], "explode", 5).status_code == 400
        assert self._post(client, [], "set", 5).status_code == 422
        assert int(self._entry(a).base_price_amount) == 1000000

    def test_page_groups_variants_by_size_and_finds_a_variant_by_barcode(self):
        a, b, c = self._priced("Bulk Group Whey", [(1250000, None), (1250000, None), (1250000, None)])
        b.barcode = "4600000000123"
        b.save(update_fields=["barcode"])

        body = _staff_client().get("/django-admin/products/price-list/", {"q": "4600000000123"}).content.decode()

        assert f'data-sub-variant-id="{a.id}"' in body
        assert f'data-group-ids="{",".join(str(v.id) for v in sorted([a, b, c], key=lambda v: v.sku))}"' in body or "data-group-ids=" in body
        assert "wx-pl-sub is-match" in body or "is-match" in body.split(f'data-sub-variant-id="{b.id}"')[0][-200:]


class TestPriceListRepositoryWritesOnlyChangedEntries:
    def test_setting_one_price_does_not_rewrite_the_other_entries(self):
        from decimal import Decimal

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.pricing.infrastructure import composition as pc
        from apps.products.infrastructure.admin import _get_or_create_default_price_list

        pl = _get_or_create_default_price_list()
        variants = [_make_variant(f"Repo Speed {i}") for i in range(15)]
        for v in variants:
            pc.build_set_price().execute(price_list_id=pl.id, product_variant_id=v.id, base_amount=Decimal(100000), currency=pl.currency)

        with CaptureQueriesContext(connection) as ctx:
            pc.build_set_price().execute(price_list_id=pl.id, product_variant_id=variants[0].id, base_amount=Decimal(120000), currency=pl.currency)

        writes = [q["sql"] for q in ctx.captured_queries if "pricing_price_list_entr" in q["sql"].lower() and q["sql"].lstrip().upper().startswith(("UPDATE", "INSERT"))]
        assert len(writes) <= 1


class TestPriceListVariantEditorStock:
    """The variant editor sets the online warehouse count through the stock ledger."""

    def _warehouse(self):
        from apps.stores.infrastructure.models import Store, StoreKind, StoreStatus

        return Store.objects.create(name=f"Main {uuid.uuid4().hex[:6]}", slug=f"main-{uuid.uuid4().hex[:6]}", kind=StoreKind.WAREHOUSE, status=StoreStatus.ACTIVE)

    def _post(self, client, variant_id, quantity):
        import json

        return client.post(f"/django-admin/products/price-list/api/stock/{variant_id}", json.dumps({"quantity": quantity}), content_type="application/json")

    def test_sets_the_count_with_one_adjustment_and_reports_it(self):
        from apps.stores.infrastructure.models import StockMovement, StoreProductStock

        store = self._warehouse()
        variant = _make_variant("Stock Editor Whey")
        client = _staff_client()

        r = self._post(client, variant.id, 7)
        assert r.status_code == 200 and r.json()["data"]["online_stock"] == 7
        assert StoreProductStock.objects.get(store=store, product_variant_id=variant.id).quantity == 7
        r = self._post(client, variant.id, 3)
        assert r.json()["data"]["online_stock"] == 3
        moves = list(StockMovement.objects.filter(store=store, product_variant_id=variant.id).order_by("created_at").values_list("movement_type", "quantity", "reference"))
        assert moves == [("adjustment", 7, "PRICE-LIST"), ("adjustment", -4, "PRICE-LIST")]
        data = client.get(f"/django-admin/products/price-list/api/product/{variant.product_id}").json()["data"]
        assert data["variants"][0]["online_stock"] == 3 and data["online_store"] == store.name

    def test_rejects_bad_numbers_reserved_units_and_non_staff(self):
        from apps.stores.infrastructure.models import StoreProductStock

        store = self._warehouse()
        variant = _make_variant("Stock Editor Reserved")
        StoreProductStock.objects.create(store=store, product_variant_id=variant.id, quantity=5, reserved_quantity=2)
        client = _staff_client()
        assert self._post(client, variant.id, -1).status_code == 422
        assert self._post(client, variant.id, "abc").status_code == 422
        assert self._post(client, variant.id, 1).status_code == 409  # 2 units are reserved
        assert StoreProductStock.objects.get(store=store, product_variant_id=variant.id).quantity == 5
        assert self._post(client, uuid.uuid4(), 1).status_code == 404
        assert self._post(Client(), variant.id, 1).status_code == 302
