"""
Storefront availability straight from the WMS stock, purchase cost (where it comes from, how receipts carry it,
margin on the receipt document), opening stock as a real goods receipt, and the new-transfer smart fill-up.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest

from apps.stores.infrastructure import availability, stock_service
from apps.stores.infrastructure.count_service import cost_info
from apps.stores.infrastructure.models import ReorderRule, StockReceipt, StockReceiptItem, StockTransfer, StockTransferItem, StoreProductStock
from apps.stores.tests.interfaces.test_wms_planning import _client, _put, _store, _variant
from common.exceptions import DomainException

pytestmark = pytest.mark.django_db


def _price(variant, price=None, cost=None):
    from apps.pricing.infrastructure.models import PriceListEntryModel, PriceListModel

    pl, _ = PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
    PriceListEntryModel.objects.create(price_list=pl, product_variant_id=variant.id, base_price_amount=Decimal(price or 0), cost_price_amount=cost)


class TestStorefrontReadsWmsStock:
    def test_sellable_is_on_hand_minus_reserved_at_active_locations(self):
        wh, shop, closed = _store("warehouse", "WH"), _store(), _store()
        closed.status = "inactive"
        closed.save(update_fields=["status"])
        v = _variant()
        _put(wh, v, 20)
        _put(shop, v, 6)
        _put(closed, v, 50)
        StoreProductStock.objects.filter(store=shop, product_variant_id=v.id).update(reserved_quantity=4)
        assert availability.sellable([v.id]) == {v.id: 22}
        # "where to buy" lists branches only, never the warehouse or a closed branch
        assert [(b["name"], b["available_quantity"]) for b in availability.branches([v.id])[v.id]] == [(shop.name, 2)]

    def test_the_old_inventory_mirror_no_longer_decides(self):
        """A drifted mirror row (64 units on the storefront, 0 on the shelf) must not be sold."""
        from apps.inventory.infrastructure.models import InventoryModel, WarehouseInventoryModel

        shop, v = _store(), _variant()
        _put(shop, v, 0)
        inv = InventoryModel.objects.create(code=f"INV-{uuid.uuid4().hex[:8]}", product_variant_id=v.id)
        WarehouseInventoryModel.objects.create(inventory=inv, warehouse_id=shop.id, available_quantity=64)
        assert availability.sellable([v.id]) == {v.id: 0}


class TestCost:
    def test_cost_source_receipt_then_catalog_then_price(self):
        wh = _store("warehouse", "WH")
        received, catalog, priced, bare = _variant(), _variant(), _variant(), _variant()
        _price(received, 200, cost=150)
        _price(catalog, 300, cost=210)
        _price(priced, 90)
        stock_service.post_receipt(wh, [{"variant_id": received.id, "quantity": 3, "unit_cost": "160"}], "Ali")
        info = cost_info([received.id, catalog.id, priced.id, bare.id])
        assert info[received.id] == (Decimal("160.00"), "receipt")
        assert info[catalog.id] == (Decimal("210.00"), "catalog")
        assert info[priced.id][1] == "price"
        assert info[bare.id] == (Decimal(0), None)

    def test_receipt_rejects_a_non_numeric_or_negative_cost(self):
        wh, v = _store("warehouse", "WH"), _variant()
        for bad in ("abc", "-5"):
            with pytest.raises(DomainException):
                stock_service.post_receipt(wh, [{"variant_id": v.id, "quantity": 1, "unit_cost": bad}], "Ali")
        assert not StockReceipt.objects.exists()

    def test_receipt_accepts_a_spaced_cost_and_lookup_prefills_it(self):
        wh, v = _store("warehouse", "WH"), _variant()
        _price(v, 250000, cost=180000)
        boss = _client(superuser=True)
        found = boss.get("/django-admin/stores/stocktransfer/api/lookup/", {"code": v.barcode, "location": wh.id}).json()["data"]
        assert (found["prefill_cost"], found["cost_source"]) == ("180000.00", "catalog")
        stock_service.post_receipt(wh, [{"variant_id": v.id, "quantity": 2, "unit_cost": "190 000"}], "Ali")
        assert StockReceiptItem.objects.get(product_variant_id=v.id).unit_cost == Decimal("190000")
        found = boss.get("/django-admin/stores/stocktransfer/api/lookup/", {"code": v.barcode, "location": wh.id}).json()["data"]
        assert (found["prefill_cost"], found["cost_source"]) == ("190000.00", "receipt")

    def test_selling_price_is_never_prefilled_as_cost(self):
        wh, v = _store("warehouse", "WH"), _variant()
        _price(v, 99000)
        found = _client(superuser=True).get("/django-admin/stores/stocktransfer/api/lookup/", {"code": v.barcode, "location": wh.id}).json()["data"]
        assert found["prefill_cost"] == "" and found["cost_source"] == "price"

    def test_receipt_document_shows_margin_and_expected_profit(self):
        wh, v = _store("warehouse", "WH"), _variant()
        _price(v, 200000)
        r = stock_service.post_receipt(wh, [{"variant_id": v.id, "quantity": 10, "unit_cost": "150000"}], "Ali")
        html = _client(superuser=True).get(f"/django-admin/stores/stockreceipt/{r.pk}/change/").content.decode()
        assert "25.0%" in html  # (200 000 − 150 000) / 200 000
        assert "500 000" in html  # 10 × 50 000 expected gross profit

    def test_new_receipt_page_ships_valid_config(self):
        _store("warehouse", "WH")
        html = _client(superuser=True).get("/django-admin/stores/stockreceipt/new/").content.decode()
        assert 'id="wms-config"' in html and "nutrizone-wms-receipt.js" in html and "/stocktransfer/new/" in html


class TestOpeningStock:
    def test_opening_stock_of_a_new_variant_is_a_goods_receipt(self):
        from apps.products.infrastructure.admin import ProductVariantAdminForm

        wh = _store("warehouse", "WH")
        v = _variant()
        form = ProductVariantAdminForm(instance=v)
        form.cleaned_data = {"stock": 12, "base_cost_price": Decimal("70000")}
        form._nz_new = True
        form._save_stock(v)
        item = StockReceiptItem.objects.get(product_variant_id=v.id)
        assert (item.receipt.store_id, item.quantity, item.unit_cost) == (wh.id, 12, Decimal("70000"))
        assert StoreProductStock.objects.get(store=wh, product_variant_id=v.id).quantity == 12

    def test_an_existing_variant_never_gets_stock_from_the_product_form(self):
        from apps.products.infrastructure.admin import ProductVariantAdminForm

        _store("warehouse", "WH")
        v = _variant()
        form = ProductVariantAdminForm(instance=v)
        form.cleaned_data = {"stock": 99}
        form._nz_new = False
        form._save_stock(v)
        assert not StockReceipt.objects.exists()


class TestTransferSuggestions:
    def test_suggests_what_the_branch_lacks_capped_by_the_source(self):
        wh, shop = _store("warehouse", "WH"), _store()
        low, fine, scarce = _variant(), _variant(), _variant()
        for v, units in ((low, 50), (fine, 50), (scarce, 3)):
            _put(wh, v, units)
        _put(shop, low, 2)
        _put(shop, fine, 30)
        ReorderRule.objects.create(store=shop, product_variant_id=low.id, min_quantity=5, target_quantity=20)
        ReorderRule.objects.create(store=shop, product_variant_id=fine.id, min_quantity=5, target_quantity=20)
        ReorderRule.objects.create(store=shop, product_variant_id=scarce.id, min_quantity=5, target_quantity=20)
        data = _client(superuser=True).get("/django-admin/stores/stocktransfer/api/suggest/", {"source": wh.id, "destination": shop.id}).json()["data"]["lines"]
        got = {ln["sku"]: (ln["suggest"], ln["out"]) for ln in data}
        assert got == {low.sku: (18, False), scarce.sku: (3, True)}
        assert data[0]["sku"] == scarce.sku  # out of stock first

    def test_new_transfer_takes_the_picked_lines(self):
        wh, shop = _store("warehouse", "WH"), _store()
        a, b = _variant(), _variant()
        _put(wh, a, 10)
        _put(wh, b, 10)
        lines = json.dumps([{"variant_id": str(a.id), "quantity": 4}, {"variant_id": str(b.id), "quantity": 2}, {"variant_id": "bad", "quantity": 1}])
        response = _client(superuser=True).post("/django-admin/stores/stocktransfer/new/", {"source": wh.id, "destination": shop.id, "lines": lines})
        assert response.status_code == 302
        t = StockTransfer.objects.get(source=wh, destination=shop)
        assert dict(StockTransferItem.objects.filter(transfer=t).values_list("product_variant_id", "expected_quantity")) == {a.id: 4, b.id: 2}

    def test_new_transfer_page_shows_location_stats(self):
        wh, shop = _store("warehouse", "WH"), _store()
        v = _variant()
        _put(wh, v, 37)
        ReorderRule.objects.create(store=shop, product_variant_id=v.id, min_quantity=5, target_quantity=10)
        html = _client(superuser=True).get("/django-admin/stores/stocktransfer/new/").content.decode()
        assert "<b>37</b>" in html and "minimumdan past" in html and "nutrizone-transfer-new.js" in html
