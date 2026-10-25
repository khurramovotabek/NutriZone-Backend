"""The cashier's own price for a basket line: sold at that price, journaled (Narx o'zgarishlari), undoable, guarded."""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import Client

from apps.pos.infrastructure.models import SaleModel
from apps.stores.infrastructure.models import PosPriceChange
from apps.stores.tests.interfaces.test_store_pos import _add, _open, _pay, shop  # noqa: F401 -- fixture

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _price(c, sale_id, line_id, price, reason=""):
    return c.patch(f"/api/v1/my-store/pos/sales/{sale_id}/items/{line_id}", {"unit_price": price, "reason": reason}, format="json")


def test_a_changed_price_is_sold_and_journaled(shop):  # noqa: F811
    c = shop["client"]
    sale = _open(c)
    line = _add(c, sale["id"], shop["whey"], 2).json()["data"]["items"][0]
    body = _price(c, sale["id"], line["id"], "100000", "doimiy mijoz").json()["data"]
    item = body["items"][0]
    assert item["unit_price"] == "100000.00" and item["list_price"] == "120000.00" and item["price_reason"] == "doimiy mijoz"
    assert body["total"] == "200000.00"

    entry = PosPriceChange.objects.get(line_id=line["id"])
    assert (entry.store, entry.list_price, entry.new_price, entry.quantity) == (shop["store"], Decimal("120000"), Decimal("100000"), 2)
    assert entry.product_name.startswith("Whey Gold") and entry.difference == Decimal("40000")

    # changed again: still one row, the original list price is kept; quantity follows the basket
    _price(c, sale["id"], line["id"], "90000")
    c.patch(f"/api/v1/my-store/pos/sales/{sale['id']}/items/{line['id']}", {"quantity": 3}, format="json")
    entry.refresh_from_db()
    assert (entry.list_price, entry.new_price, entry.quantity) == (Decimal("120000"), Decimal("90000"), 3)

    done = _pay(c, sale["id"]).json()["data"]
    assert done["status"] == "completed" and done["total"] == "270000.00"
    assert SaleModel.objects.get(id=sale["id"]).status == "completed"


def test_back_to_the_list_price_or_removing_the_line_drops_the_journal_entry(shop):  # noqa: F811
    c = shop["client"]
    sale = _open(c)
    line = _add(c, sale["id"], shop["whey"]).json()["data"]["items"][0]
    _price(c, sale["id"], line["id"], "110000")
    assert PosPriceChange.objects.count() == 1
    item = _price(c, sale["id"], line["id"], "120000").json()["data"]["items"][0]
    assert item["list_price"] is None and not PosPriceChange.objects.exists()

    _price(c, sale["id"], line["id"], "110000")
    c.delete(f"/api/v1/my-store/pos/sales/{sale['id']}/items/{line['id']}")
    assert not PosPriceChange.objects.exists()


def test_nonsense_prices_are_refused(shop):  # noqa: F811
    c = shop["client"]
    sale = _open(c)
    line = _add(c, sale["id"], shop["creatine"]).json()["data"]["items"][0]
    assert _price(c, sale["id"], line["id"], "0").status_code == 422
    assert _price(c, sale["id"], line["id"], "abc").status_code == 422
    assert _price(c, sale["id"], line["id"], "8000000").status_code == 409  # 100x the 80 000 list price: a typo
    assert c.get(f"/api/v1/my-store/pos/sales/{sale['id']}").json()["data"]["total"] == "80000.00"


def test_dashboard_journal_lists_the_change(shop):  # noqa: F811
    c = shop["client"]
    sale = _open(c)
    line = _add(c, sale["id"], shop["whey"]).json()["data"]["items"][0]
    _price(c, sale["id"], line["id"], "100000", "ulgurji")
    _pay(c, sale["id"])
    admin = StaffUser.objects.create_superuser("journal_admin", "j@example.com", "x")
    staff = Client()
    staff.force_login(admin)
    page = staff.get("/django-admin/stores/pospricechange/", HTTP_ACCEPT_LANGUAGE="uz")
    html = page.content.decode()
    assert page.status_code == 200 and "Whey Gold" in html and "120 000" in html and "100 000" in html and "ulgurji" in html and "Sotildi" in html
