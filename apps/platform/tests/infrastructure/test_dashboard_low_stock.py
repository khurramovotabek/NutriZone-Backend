"""Dashboard home low-stock reads the WMS (StoreProductStock + ReorderRule), not the retired inventory mirror."""
from __future__ import annotations

import pytest

from apps.platform.infrastructure.dashboard_home import wms_low_stock
from apps.stores.infrastructure.models import ReorderRule
from apps.stores.tests.interfaces.test_wms_planning import _put, _store, _variant

pytestmark = pytest.mark.django_db


def test_lists_products_at_or_below_their_minimum_empty_shelves_first():
    shop = _store()
    low, empty, fine = _variant(), _variant(), _variant()
    _put(shop, low, 3)
    _put(shop, fine, 50)
    for v in (low, empty, fine):
        ReorderRule.objects.create(store=shop, product_variant_id=v.id, min_quantity=5, target_quantity=20)

    items = [i for i in wms_low_stock() if i["store_id"] == str(shop.id)]

    assert [i["available_quantity"] for i in items] == [0, 3]
    assert items[0]["code"].startswith(empty.sku)
    assert items[1]["low_stock_at"] == 5
