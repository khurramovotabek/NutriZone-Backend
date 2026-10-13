"""
Stock count (Inventarizatsiya): snapshot → count → review (reasons) → post adjusts live stock through the ledger,
sales during the count are respected, reserved units are protected, blind counts hide the system quantity,
and the premium WMS pages render.
"""
from __future__ import annotations

import json
import uuid

import pytest
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.models import User as StaffUser
from django.db import transaction
from django.test import Client

from apps.stores.infrastructure import count_service, stock_service
from apps.stores.infrastructure.models import StockCount, StockMovement, Store, StoreProductStock
from apps.stores.tests.interfaces.test_my_store_products import _make_variant
from common.exceptions import DomainException

pytestmark = pytest.mark.django_db


@pytest.fixture
def shop():
    return Store.objects.create(id=uuid.uuid4(), name="Count shop", slug=f"cs-{uuid.uuid4().hex[:6]}", kind="store")


def _put(store, qty, reserve=0):
    v = _make_variant(barcode=f"478{uuid.uuid4().int % 10**10:010d}", status="active")
    with transaction.atomic():
        stock_service.move(store, v.id, qty, "receipt", reference="T", mirror=False)
        if reserve:
            stock_service.move(store, v.id, 0, "reservation", reserve=reserve, reference="T", mirror=False)
    return v


def _qty(store, v):
    row = StoreProductStock.objects.get(store=store, product_variant_id=v.id)
    return row.quantity, row.reserved_quantity


def _item(c, v):
    return c.items.get(product_variant_id=v.id)


class TestCountService:
    def test_full_count_posts_differences_with_reasons(self, shop):
        a, b, c_ = _put(shop, 10), _put(shop, 4), _put(shop, 7)
        c = count_service.start(shop.id, "Ali", scope="full")
        assert c.items.count() == 3 and _item(c, a).expected_quantity == 10
        count_service.save_counts(c.id, "Ali", {str(_item(c, a).id): 8, str(_item(c, b).id): 4, str(_item(c, c_).id): 9})
        count_service.submit(c.id, "Ali")
        with pytest.raises(DomainException):  # every difference needs a reason
            count_service.post(c.id, "Boss")
        count_service.save_reasons(c.id, "Boss", {str(_item(c, a).id): {"reason": "damaged"}, str(_item(c, c_).id): {"reason": "unrecorded_receipt"}})
        c = count_service.post(c.id, "Boss")
        assert (c.status, c.lines_matched, c.shortage_units, c.excess_units) == ("posted", 1, 2, 2)
        assert _qty(shop, a)[0] == 8 and _qty(shop, b)[0] == 4 and _qty(shop, c_)[0] == 9
        kinds = dict(StockMovement.objects.filter(reference=c.number).values_list("product_variant_id", "movement_type"))
        assert kinds == {a.id: "damage", c_.id: "adjustment"}

    def test_sales_during_the_count_are_kept(self, shop):
        v = _put(shop, 10)
        c = count_service.start(shop.id, "Ali")
        with transaction.atomic():  # a till sells 3 while the count is running
            stock_service.move(shop, v.id, -3, "sale", reference="POS-1", mirror=False)
        count_service.save_counts(c.id, "Ali", {str(_item(c, v).id): 9})  # counted 9 of the snapshot's 10 -> 1 missing
        count_service.submit(c.id, "Ali")
        count_service.save_reasons(c.id, "Boss", {str(_item(c, v).id): {"reason": "lost"}})
        count_service.post(c.id, "Boss")
        assert _qty(shop, v)[0] == 6  # 10 - 3 sold - 1 missing

    def test_shortage_never_eats_reserved_units(self, shop):
        v = _put(shop, 5, reserve=4)
        c = count_service.start(shop.id, "Ali")
        count_service.save_counts(c.id, "Ali", {str(_item(c, v).id): 0})
        count_service.submit(c.id, "Ali")
        count_service.save_reasons(c.id, "Boss", {str(_item(c, v).id): {"reason": "lost"}})
        count_service.post(c.id, "Boss")
        assert _qty(shop, v) == (4, 4)
        assert _item(StockCount.objects.get(pk=c.pk), v).adjusted_quantity == -1

    def test_uncounted_lines_and_zero_option(self, shop):
        v = _put(shop, 3)
        c = count_service.start(shop.id, "Ali")
        with pytest.raises(DomainException):
            count_service.submit(c.id, "Ali")
        count_service.submit(c.id, "Ali", uncounted_as_zero=True)
        assert _item(StockCount.objects.get(pk=c.pk), v).counted_quantity == 0

    def test_one_open_count_per_location_and_found_products(self, shop):
        _put(shop, 1)
        c = count_service.start(shop.id, "Ali")
        with pytest.raises(DomainException):
            count_service.start(shop.id, "Vali")
        extra = _make_variant(barcode=f"478{uuid.uuid4().int % 10**10:010d}", status="active")
        made = count_service.add_products(c.id, "Ali", [extra.id])
        assert made and made[0].added_during_count and made[0].expected_quantity == 0

    def test_cancel_changes_nothing(self, shop):
        v = _put(shop, 6)
        c = count_service.start(shop.id, "Ali")
        count_service.save_counts(c.id, "Ali", {str(_item(c, v).id): 1})
        count_service.cancel(c.id, "Ali", "wrong shop")
        assert _qty(shop, v)[0] == 6 and StockCount.objects.get(pk=c.pk).status == "cancelled"


class TestCountAdmin:
    def _client(self, perms=None, superuser=False):
        if superuser:
            user = StaffUser.objects.create_superuser(username=f"cnt_{uuid.uuid4().hex[:6]}", password="test-pass-12345", first_name="Dilnoza")
        else:
            user = StaffUser.objects.create_user(username=f"cnt_{uuid.uuid4().hex[:6]}", password="test-pass-12345", is_staff=True)
            user.user_permissions.add(*Permission.objects.filter(content_type__app_label="stores", codename__in=perms or []))
        client = Client()
        client.force_login(user)
        return client

    def test_full_flow_through_the_dashboard(self, shop):
        v = _put(shop, 5)
        boss = self._client(superuser=True)
        resp = boss.post("/django-admin/stores/stockcount/new/", {"store": str(shop.id), "scope": "full", "blind": "1"})
        c = StockCount.objects.get(store=shop)
        assert resp.status_code == 302 and resp["Location"].endswith(f"/{c.pk}/work/")
        do = f"/django-admin/stores/stockcount/{c.pk}/do/"
        item = _item(c, v)
        scan = boss.post(do + "scan/", json.dumps({"code": v.barcode}), content_type="application/json").json()
        assert scan["ok"] and scan["added"] is False  # already on the list
        assert boss.post(do + "save_counts/", json.dumps({"counts": {str(item.id): 4}}), content_type="application/json").json()["ok"]
        assert boss.post(do + "submit/", "{}", content_type="application/json").json()["ok"]
        posted = boss.post(do + "post/", json.dumps({"reasons": {str(item.id): {"reason": "expired", "note": "2025 batch"}}}), content_type="application/json").json()
        assert posted["ok"] and posted["data"]["status"] == "posted"
        assert _qty(shop, v)[0] == 4
        assert boss.get(f"/django-admin/stores/stockcount/{c.pk}/act/").status_code == 200
        assert boss.get(f"/django-admin/stores/stockcount/{c.pk}/report.xlsx").status_code == 200

    def test_counters_cannot_post_and_blind_hides_the_system_quantity(self, shop):
        v = _put(shop, 5)
        counter = self._client(perms=["view_stockcount", "add_stockcount", "change_stockcount"])
        counter.post("/django-admin/stores/stockcount/new/", {"store": str(shop.id), "scope": "full", "blind": "1"})
        c = StockCount.objects.get(store=shop)
        data = counter.get(f"/django-admin/stores/stockcount/{c.pk}/data/").json()["data"]
        assert data["hidden"] is True and data["items"][0]["expected"] is None
        item = _item(c, v)
        do = f"/django-admin/stores/stockcount/{c.pk}/do/"
        counter.post(do + "save_counts/", json.dumps({"counts": {str(item.id): 5}}), content_type="application/json")
        counter.post(do + "submit/", "{}", content_type="application/json")
        assert counter.post(do + "post/", "{}", content_type="application/json").status_code == 403

    def test_role_groups_got_the_count_permissions(self):
        assert Group.objects.get(name="Sklad menejeri").permissions.filter(codename="post_stockcount").exists()
        assert not Group.objects.get(name="Sklad operatori").permissions.filter(codename="post_stockcount").exists()


class TestPremiumWmsPages:
    def test_pages_render(self, shop):
        _put(shop, 3)
        boss = Client()
        boss.force_login(StaffUser.objects.create_superuser(username=f"wms_{uuid.uuid4().hex[:6]}", password="x-pass-12345"))
        for url in (f"/django-admin/wms/stock/?location={shop.id}", f"/django-admin/wms/stock/?location={shop.id}&state=low", "/django-admin/wms/stock/?view=matrix",
                    "/django-admin/stores/stocktransfer/", "/django-admin/stores/stockreceipt/", "/django-admin/stores/stockmovement/",
                    "/django-admin/stores/stockmovement/export.xlsx", "/django-admin/stores/stockcount/", "/django-admin/stores/stockcount/new/"):
            assert boss.get(url).status_code == 200, url
