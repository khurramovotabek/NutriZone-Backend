"""
Ombor → Qoldiqlar: the "On hand" count edited in place, and a whole branch made equal to the OX (ox-sys) count --
always through the ledger (ADJUSTMENT), never below the reservation.
"""
from __future__ import annotations

import json

import pytest

from apps.stores.infrastructure import stock_sync
from apps.stores.infrastructure.models import StockMovement, StockMovementType
from apps.stores.tests.interfaces.test_wms_planning import _client, _put, _qty, _store, _variant

pytestmark = pytest.mark.django_db
SET = "/django-admin/wms/stock/api/set/"
SYNC = "/django-admin/wms/stock/api/sync/"


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type="application/json")


class TestSetFromTheList:
    def test_sets_the_count_through_the_ledger(self):
        shop, v = _store(), _variant()
        _put(shop, v, 10)
        r = _post(_client(superuser=True), SET, {"location": str(shop.id), "variant": str(v.id), "quantity": 7})
        assert r.status_code == 200
        assert r.json()["data"] == {"quantity": 7, "reserved": 0, "available": 7, "before": 10, "clamped": False, "state": "ok"}
        assert _qty(shop, v) == (7, 0)
        m = StockMovement.objects.filter(store=shop, product_variant_id=v.id, movement_type=StockMovementType.ADJUSTMENT).get()
        assert m.quantity == -3 and m.reference == "STOCK-LIST" and "10 → 7" in m.note

    def test_a_product_the_branch_never_had_can_be_counted_in(self):
        shop, v = _store(), _variant()
        r = _post(_client(superuser=True), SET, {"location": str(shop.id), "variant": str(v.id), "quantity": "4"})
        assert r.json()["data"]["quantity"] == 4 and _qty(shop, v) == (4, 0)

    def test_never_below_the_reservation(self):
        shop, v = _store(), _variant()
        _put(shop, v, 10, reserve=3)
        data = _post(_client(superuser=True), SET, {"location": str(shop.id), "variant": str(v.id), "quantity": 1}).json()["data"]
        assert data["quantity"] == 3 and data["clamped"] and data["available"] == 0 and data["state"] == "out"
        assert _qty(shop, v) == (3, 3)

    @pytest.mark.parametrize("bad", [-1, "abc", "", 2_000_000])
    def test_rejects_bad_numbers(self, bad):
        shop, v = _store(), _variant()
        _put(shop, v, 5)
        assert _post(_client(superuser=True), SET, {"location": str(shop.id), "variant": str(v.id), "quantity": bad}).status_code == 400
        assert _qty(shop, v) == (5, 0)

    def test_needs_permission(self):
        shop, v = _store(), _variant()
        _put(shop, v, 5)
        assert _post(_client(perms=[]), SET, {"location": str(shop.id), "variant": str(v.id), "quantity": 1}).status_code == 403
        assert _post(_client(perms=["change_storeproductstock"]), SET, {"location": str(shop.id), "variant": str(v.id), "quantity": 1}).status_code == 200

    def test_page_shows_the_editor_only_to_those_who_may_edit(self):
        shop, v = _store(), _variant()
        _put(shop, v, 5)
        assert "data-qty-edit" in _client(superuser=True).get(f"/django-admin/wms/stock/?location={shop.id}").content.decode()
        assert "data-qty-edit" not in _client(perms=["view_storeproductstock"]).get(f"/django-admin/wms/stock/?location={shop.id}").content.decode()


class TestSyncFromOx:
    def test_dry_run_reports_and_changes_nothing_then_applies(self):
        shop, up, down, same, ours_only = _store(), _variant(), _variant(), _variant(), _variant()
        _put(shop, up, 1)
        _put(shop, down, 9)
        _put(shop, same, 4)
        _put(shop, ours_only, 2)
        counts = [[up.barcode, 6, "UP"], [down.barcode, 0, "DOWN"], [same.barcode, 4, "SAME"], ["999000111222", 5, "NOT IN CATALOGUE"]]
        boss = _client(superuser=True)
        dry = _post(boss, SYNC, {"location": str(shop.id), "counts": counts}).json()["data"]
        assert dry["dry_run"] and dry["matched"] == 3 and dry["unchanged"] == 1
        assert (dry["raised"], dry["raised_units"], dry["lowered"], dry["lowered_units"]) == (1, 5, 1, -9)
        assert dry["unknown"] == 1 and dry["unknown_units"] == 5 and dry["not_in_source"] == 1
        assert _qty(shop, up) == (1, 0) and _qty(shop, down) == (9, 0)
        done = _post(boss, SYNC, {"location": str(shop.id), "counts": counts, "dry_run": False}).json()["data"]
        assert not done["dry_run"]
        assert _qty(shop, up) == (6, 0) and _qty(shop, down) == (0, 0) and _qty(shop, same) == (4, 0)
        assert _qty(shop, ours_only) == (2, 0)  # OX doesn't list it -> reported, untouched
        assert StockMovement.objects.filter(store=shop, reference="OX-SYNC").count() == 2

    def test_leading_zeros_extra_barcodes_and_reservations(self):
        from apps.products.infrastructure.models import ProductVariantBarcode

        shop, a, b = _store(), _variant(), _variant()
        ProductVariantBarcode.objects.create(variant=b, barcode="0748927000111")
        _put(shop, a, 10, reserve=4)
        rep = stock_sync.sync_counts(shop, [["0" + a.barcode, 1], ["748927000111", 3], [b.barcode, 2]], actor="t", dry_run=False)
        assert _qty(shop, a) == (4, 4) and len(rep.clamped) == 1  # reserved units stay
        assert _qty(shop, b) == (5, 0)  # main + extra barcode of one product add up

    def test_sync_needs_count_permission(self):
        shop = _store()
        assert _post(_client(perms=["change_storeproductstock"]), SYNC, {"location": str(shop.id), "counts": []}).status_code == 403
        assert _post(_client(perms=["post_stockcount"]), SYNC, {"location": str(shop.id), "counts": []}).status_code == 200
