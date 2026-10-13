"""
"Where is it and how much": the per-product stock page, the matrix's catalogue scope / gap filters, the location
view's "missing here" tab, scanner redirects and the transfer form prefilled from those pages.
"""
from __future__ import annotations

import pytest

from apps.stores.infrastructure.models import ReorderRule, StockTransfer, StockTransferItem
from apps.stores.tests.interfaces.test_wms_planning import _client, _put, _store, _variant

pytestmark = pytest.mark.django_db


class TestProductStockPage:
    def test_lists_every_location_with_state_against_its_minimum(self):
        wh, shop, empty = _store("warehouse", "WH"), _store(name="Olmazor"), _store(name="Chilonzor")
        v = _variant()
        _put(wh, v, 40)
        _put(shop, v, 3)
        ReorderRule.objects.create(store=shop, product_variant_id=v.id, min_quantity=5, target_quantity=12)
        page = _client(superuser=True).get(f"/django-admin/wms/stock/product/{v.id}/")
        assert page.status_code == 200
        html = page.content.decode()
        assert wh.name in html and shop.name in html and empty.name in html
        assert "min 5" in html
        # the low branch gets a one-click top-up from the warehouse, sized up to the rule's target (12 - 3)
        assert f"source={wh.id}&amp;destination={shop.id}&amp;variant={v.id}&amp;quantity=9" in html

    def test_unknown_variant_is_404(self):
        import uuid

        assert _client(superuser=True).get(f"/django-admin/wms/stock/product/{uuid.uuid4()}/").status_code == 404


class TestMatrixAndMissing:
    def test_catalogue_scope_and_gap_filters(self):
        wh, shop = _store("warehouse", "WH"), _store()
        held, nowhere = _variant(), _variant()
        _put(wh, held, 10)
        boss = _client(superuser=True)
        default = boss.get("/django-admin/wms/stock/?view=matrix").content.decode()
        assert held.sku in default and nowhere.sku not in default
        assert nowhere.sku in boss.get("/django-admin/wms/stock/?view=matrix&scope=all").content.decode()
        assert held.sku in boss.get("/django-admin/wms/stock/?view=matrix&gap=some").content.decode()  # 0 in the shop
        gap_none = boss.get("/django-admin/wms/stock/?view=matrix&gap=none").content.decode()
        assert nowhere.sku in gap_none and held.sku not in gap_none
        assert boss.get("/django-admin/wms/stock/?view=matrix&scope=all&export=xlsx").status_code == 200

    def test_missing_here_offers_a_transfer_from_where_it_is(self):
        wh, shop = _store("warehouse", "WH"), _store()
        v = _variant()
        _put(wh, v, 7)
        html = _client(superuser=True).get(f"/django-admin/wms/stock/?location={shop.id}&state=missing").content.decode()
        assert v.sku in html
        assert f"source={wh.id}&amp;destination={shop.id}&amp;variant={v.id}" in html

    def test_scanning_a_barcode_opens_the_product_page(self):
        wh = _store("warehouse", "WH")
        v = _variant()
        _put(wh, v, 2)
        response = _client(superuser=True).get(f"/django-admin/wms/stock/?view=matrix&q={v.barcode}")
        assert response.status_code == 302 and response["Location"].endswith(f"/wms/stock/product/{v.id}/")


class TestPrefilledTransfer:
    def test_new_transfer_carries_the_product_line(self):
        wh, shop = _store("warehouse", "WH"), _store()
        v = _variant()
        _put(wh, v, 20)
        boss = _client(superuser=True)
        form = boss.get(f"/django-admin/stores/stocktransfer/new/?source={wh.id}&destination={shop.id}&variant={v.id}&quantity=4").content.decode()
        assert v.sku in form and f'value="{shop.id}" checked' in form
        response = boss.post("/django-admin/stores/stocktransfer/new/", {"source": wh.id, "destination": shop.id, "variant": v.id, "quantity": "4"})
        assert response.status_code == 302
        t = StockTransfer.objects.get(source=wh, destination=shop)
        assert list(StockTransferItem.objects.filter(transfer=t).values_list("product_variant_id", "expected_quantity")) == [(v.id, 4)]

    def test_too_many_units_still_creates_the_draft_with_a_warning(self):
        wh, shop = _store("warehouse", "WH"), _store()
        v = _variant()
        _put(wh, v, 2)
        response = _client(superuser=True).post("/django-admin/stores/stocktransfer/new/", {"source": wh.id, "destination": shop.id, "variant": v.id, "quantity": "50"}, follow=True)
        assert response.status_code == 200
        t = StockTransfer.objects.get(source=wh, destination=shop)
        assert not StockTransferItem.objects.filter(transfer=t).exists()
