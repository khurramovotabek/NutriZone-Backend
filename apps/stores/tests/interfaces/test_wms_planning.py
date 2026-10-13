"""
Write-offs (reserve → approve deducts / reject releases), suppliers and accounts payable (receipt → debt, FIFO
settlement, overdue, statement), reorder points / replenishment (needs, incoming, transfer draft) and the
expiry view (FIFO batch estimate, buckets, FEFO) -- services and dashboard pages.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User as StaffUser
from django.db import transaction
from django.test import Client
from django.utils import timezone

from apps.stores.infrastructure import planning_service as plan
from apps.stores.infrastructure import stock_service, supplier_service, writeoff_service
from apps.stores.infrastructure.models import (
    ReorderRule,
    StockMovement,
    StockReceipt,
    StockTransfer,
    Store,
    StoreProductStock,
    Supplier,
    WriteOff,
)
from apps.stores.tests.interfaces.test_my_store_products import _make_variant
from common.exceptions import DomainException

pytestmark = pytest.mark.django_db


def _store(kind="store", name="Shop"):
    return Store.objects.create(id=uuid.uuid4(), name=f"{name} {uuid.uuid4().hex[:4]}", slug=f"wp-{uuid.uuid4().hex[:8]}", kind=kind)


def _variant():
    return _make_variant(barcode=f"479{uuid.uuid4().int % 10**10:010d}", status="active")


def _put(store, v, qty, **kw):
    with transaction.atomic():
        stock_service.move(store, v.id, qty, "receipt", reference="T", mirror=False, **kw)


def _qty(store, v):
    row = StoreProductStock.objects.get(store=store, product_variant_id=v.id)
    return row.quantity, row.reserved_quantity


def _client(perms=None, superuser=False):
    if superuser:
        user = StaffUser.objects.create_superuser(username=f"wp_{uuid.uuid4().hex[:6]}", password="test-pass-12345", first_name="Dilnoza")
    else:
        user = StaffUser.objects.create_user(username=f"wp_{uuid.uuid4().hex[:6]}", password="test-pass-12345", is_staff=True)
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label="stores", codename__in=perms or []))
    client = Client()
    client.force_login(user)
    return client


class TestWriteOffs:
    def test_submit_reserves_and_approve_deducts_by_reason(self):
        shop, a, b = _store(), _variant(), _variant()
        _put(shop, a, 10)
        _put(shop, b, 5)
        w = writeoff_service.create(shop.id, "Ali", [{"variant_id": a.id, "quantity": 2, "reason": "expired"}, {"variant_id": b.id, "quantity": 1, "reason": "tester"}])
        assert w.status == "pending" and w.total_units == 3
        assert _qty(shop, a) == (10, 2)  # set aside, not sellable
        writeoff_service.approve(w.id, "Boss")
        assert _qty(shop, a) == (8, 0) and _qty(shop, b) == (4, 0)
        kinds = dict(StockMovement.objects.filter(reference=w.number, quantity__lt=0).exclude(movement_type="release").values_list("product_variant_id", "movement_type"))
        assert kinds == {a.id: "expired", b.id: "write_off"}

    def test_reject_and_cancel_release_the_units(self):
        shop, v = _store(), _variant()
        _put(shop, v, 4)
        w = writeoff_service.create(shop.id, "Ali", [{"variant_id": v.id, "quantity": 3, "reason": "damaged"}])
        with pytest.raises(DomainException):
            writeoff_service.reject(w.id, "Boss", "")  # a reason is required
        writeoff_service.reject(w.id, "Boss", "Not broken")
        assert _qty(shop, v) == (4, 0) and WriteOff.objects.get(pk=w.pk).status == "rejected"
        w2 = writeoff_service.create(shop.id, "Ali", [{"variant_id": v.id, "quantity": 1, "reason": "lost"}])
        writeoff_service.cancel(w2.id, "Ali")
        assert _qty(shop, v) == (4, 0)
        with pytest.raises(DomainException):
            writeoff_service.approve(w2.id, "Boss")  # already closed

    def test_cannot_write_off_more_than_available(self):
        shop, v = _store(), _variant()
        _put(shop, v, 2)
        with pytest.raises(DomainException):
            writeoff_service.create(shop.id, "Ali", [{"variant_id": v.id, "quantity": 3, "reason": "damaged"}])
        assert not WriteOff.objects.filter(store=shop).exists() and _qty(shop, v) == (2, 0)

    def test_dashboard_flow_and_permissions(self):
        shop, v = _store(), _variant()
        _put(shop, v, 6)
        clerk = _client(perms=["view_writeoff", "add_writeoff"])
        assert clerk.get(f"/django-admin/stores/writeoff/new/?store={shop.id}&variant={v.id}&qty=2&reason=expired").status_code == 200
        denied = clerk.post("/django-admin/stores/writeoff/new/post/", json.dumps({"location": str(shop.id), "approve": True, "lines": [{"variant_id": str(v.id), "quantity": 1, "reason": "damaged"}]}), content_type="application/json")
        assert denied.status_code == 403
        made = clerk.post("/django-admin/stores/writeoff/new/post/", json.dumps({"location": str(shop.id), "lines": [{"variant_id": str(v.id), "quantity": 2, "reason": "damaged"}]}), content_type="application/json").json()
        w = WriteOff.objects.get(number=made["data"]["number"])
        assert clerk.get(made["data"]["url"]).status_code == 200
        assert clerk.post(f"/django-admin/stores/writeoff/{w.pk}/decide/", {"action": "approve"}).status_code == 403
        boss = _client(superuser=True)
        boss.post(f"/django-admin/stores/writeoff/{w.pk}/decide/", {"action": "approve"})
        assert WriteOff.objects.get(pk=w.pk).status == "approved" and _qty(shop, v) == (4, 0)
        assert boss.get("/django-admin/stores/writeoff/").status_code == 200


class TestSuppliers:
    def test_receipt_creates_supplier_debt_and_due_date(self):
        wh, v = _store("warehouse", "WH"), _variant()
        Supplier.objects.create(name="Optimum Distr", payment_terms_days=10)
        r = stock_service.post_receipt(wh, [{"variant_id": v.id, "quantity": 4, "unit_cost": "25000"}], "Ali", supplier="  optimum   distr ")
        assert r.supplier_ref.name == "Optimum Distr" and r.due_date == timezone.localdate() + timedelta(days=10)
        r2 = stock_service.post_receipt(wh, [{"variant_id": v.id, "quantity": 1}], "Ali", supplier="Brand New LLC")
        assert Supplier.objects.filter(name="Brand New LLC").exists() and r2.total_value == 0
        b = supplier_service.balance(r.supplier_ref)
        assert b.purchased == Decimal("100000") and b.debt == Decimal("100000") and b.overdue == 0

    def test_payments_settle_oldest_first_and_overdue(self):
        wh, v = _store("warehouse", "WH"), _variant()
        s = Supplier.objects.create(name=f"Sup {uuid.uuid4().hex[:4]}", payment_terms_days=0)
        old = stock_service.post_receipt(wh, [{"variant_id": v.id, "quantity": 10, "unit_cost": "1000"}], "Ali", supplier=s.name)
        new = stock_service.post_receipt(wh, [{"variant_id": v.id, "quantity": 5, "unit_cost": "1000"}], "Ali", supplier=s.name)
        StockReceipt.objects.filter(pk=old.pk).update(due_date=timezone.localdate() - timedelta(days=5))
        supplier_service.add_payment(s, "Boss", "4 000", method="cash")
        b = supplier_service.balance(s)
        assert b.debt == Decimal("11000") and b.overdue == Decimal("6000")
        assert b.receipt_status[old.pk]["status"] == "overdue" and b.receipt_status[new.pk]["status"] == "open"
        supplier_service.add_payment(s, "Boss", 11000)
        b = supplier_service.balance(s)
        assert b.debt == 0 and b.overdue == 0 and b.receipt_status[new.pk]["status"] == "paid"
        st = supplier_service.statement(s)
        assert [r["balance"] for r in st["rows"]] == [Decimal("10000"), Decimal("15000"), Decimal("11000"), Decimal("0")]
        with pytest.raises(DomainException):
            supplier_service.add_payment(s, "Boss", "-5")
        with pytest.raises(DomainException):
            supplier_service.add_payment(s, "Boss", 5, paid_on=(timezone.localdate() + timedelta(days=2)).isoformat())

    def test_pages(self):
        wh, v = _store("warehouse", "WH"), _variant()
        r = stock_service.post_receipt(wh, [{"variant_id": v.id, "quantity": 2, "unit_cost": "5000"}], "Ali", supplier="Card Test Co")
        s = r.supplier_ref
        boss = _client(superuser=True)
        for url in ("/django-admin/stores/supplier/", "/django-admin/stores/supplier/?debt=yes", "/django-admin/stores/supplier/?debt=overdue",
                    f"/django-admin/stores/supplier/{s.pk}/card/", f"/django-admin/stores/supplier/{s.pk}/card/?from=2020-01-01",
                    f"/django-admin/stores/supplier/{s.pk}/statement.xlsx", f"/django-admin/stores/stockreceipt/{r.pk}/change/"):
            assert boss.get(url).status_code == 200, url
        boss.post(f"/django-admin/stores/supplier/{s.pk}/pay/", {"amount": "10000", "paid_on": timezone.localdate().isoformat(), "method": "bank"})
        assert supplier_service.balance(s).debt == 0
        viewer = _client(perms=["view_supplier"])
        assert viewer.post(f"/django-admin/stores/supplier/{s.pk}/pay/", {"amount": "1"}).status_code == 403


class TestReplenishment:
    def test_needs_incoming_and_transfer_draft(self):
        wh, shop, a, b = _store("warehouse", "WH"), _store(), _variant(), _variant()
        _put(wh, a, 50)
        _put(wh, b, 3)
        _put(shop, a, 2)
        plan.save_rules(shop, "Boss", {str(a.id): {"min": 5, "target": 20}, str(b.id): {"min": 2, "target": 10}})
        p = plan.plan(shop, wh)
        lines = {ln.variant_id: ln for ln in p["lines"]}
        assert lines[a.id].needs and lines[a.id].suggest == 18 and lines[a.id].can_send == 18
        assert lines[b.id].state == "out" and lines[b.id].suggest == 10 and lines[b.id].can_send == 3  # capped by the warehouse
        t = plan.create_transfer(shop, wh, "Boss", {a.id: 18, b.id: 3})
        assert t.status == "draft" and t.items.count() == 2
        again = {ln.variant_id: ln for ln in plan.plan(shop, wh)["lines"]}
        assert again[a.id].incoming == 18 and not again[a.id].needs  # the draft already covers it
        assert plan.overview()[shop.id]["rules"] == 2

    def test_rules_validation_and_removal(self):
        shop, v = _store(), _variant()
        with pytest.raises(DomainException):
            plan.save_rules(shop, "Boss", {str(v.id): {"min": 9, "target": 3}})
        plan.save_rules(shop, "Boss", {str(v.id): {"min": 1, "target": 3}})
        plan.save_rules(shop, "Boss", {str(v.id): None})
        assert not ReorderRule.objects.filter(store=shop).exists()

    def test_sales_speed_suggests_a_rule(self):
        shop, v = _store(), _variant()
        _put(shop, v, 100)
        with transaction.atomic():
            stock_service.move(shop, v.id, -30, "sale", reference="POS", mirror=False)
        assert plan.sales_map(shop)[v.id] == 30
        assert plan.suggested_rule(30) == (7, 21)
        assert plan.plan(shop, None)["norule"][0].variant_id == v.id

    def test_page_and_transfer_endpoint(self):
        wh, shop, v = _store("warehouse", "WH"), _store(), _variant()
        _put(wh, v, 20)
        boss = _client(superuser=True)
        assert boss.post("/django-admin/stores/reorderrule/save/", json.dumps({"location": str(shop.id), "rules": {str(v.id): {"min": 2, "target": 8}}}), content_type="application/json").json()["ok"]
        for tab in ("need", "rules", "norule"):
            assert boss.get(f"/django-admin/stores/reorderrule/?location={shop.id}&tab={tab}").status_code == 200
        resp = boss.post("/django-admin/stores/reorderrule/transfer/", {"location": str(shop.id), "source": str(wh.id), f"qty_{v.id}": "8", f"pick_{v.id}": "1"})
        t = StockTransfer.objects.get(destination=shop)
        assert resp.status_code == 302 and str(t.pk) in resp["Location"] and t.items.get().expected_quantity == 8


class TestExpiry:
    def test_batches_fefo_sales_skip_expired_and_buckets(self):
        shop, v = _store(), _variant()
        today = timezone.localdate()
        _put(shop, v, 5, batch_number="OLD", expiry_date=today - timedelta(days=3))
        _put(shop, v, 4, batch_number="MID", expiry_date=today + timedelta(days=20))
        _put(shop, v, 6, batch_number="NEW", expiry_date=today + timedelta(days=200))
        with transaction.atomic():
            m = stock_service.move(shop, v.id, -2, "sale", reference="POS", mirror=False)
        assert m.allocations == [{"batch": "MID", "expiry": (today + timedelta(days=20)).isoformat(), "qty": 2}] and m.batch_number == "MID"
        assert {ly.batch: ly.quantity for ly in plan.layers([shop.id])} == {"OLD": 5, "MID": 2, "NEW": 6}  # the expired batch isn't sold
        assert plan.bucket(-1) == "expired" and plan.bucket(0) == "d30" and plan.bucket(45) == "d60" and plan.bucket(200) == "ok" and plan.bucket(None) == "unknown"
        rep = plan.expiry_report([shop.id])
        assert rep["fefo"][(shop.id, v.id)].batch == "MID"
        with transaction.atomic():  # a write-off of the expired batch takes exactly that batch
            stock_service.move(shop, v.id, -5, "expired", batch_number="OLD", expiry_date=today - timedelta(days=3), mirror=False)
        assert {ly.batch: ly.quantity for ly in plan.layers([shop.id])} == {"MID": 2, "NEW": 6}

    def test_transfer_carries_batches_and_returns_restore_them(self):
        from apps.stores.infrastructure import transfer_service

        wh, shop, v = _store("warehouse", "WH"), _store(), _variant()
        today = timezone.localdate()
        _put(wh, v, 3, batch_number="A", expiry_date=today + timedelta(days=40))
        _put(wh, v, 5, batch_number="B", expiry_date=today + timedelta(days=300))
        t = transfer_service.create(wh.id, shop.id, "Ali")
        transfer_service.update_draft(t.id, "Ali", [{"variant_id": v.id, "quantity": 4}])
        transfer_service.mark_ready(t.id, "Ali")
        item = t.items.get()
        transfer_service.dispatch(t.id, "Ali", picked={str(item.id): 4})
        transfer_service.confirm_receipt(t.id, "Vali", counts={str(item.id): 4})
        assert {ly.batch: ly.quantity for ly in plan.layers([shop.id])} == {"A": 3, "B": 1}
        assert {ly.batch: ly.quantity for ly in plan.layers([wh.id])} == {"B": 4}
        with transaction.atomic():
            stock_service.move(shop, v.id, -3, "sale", reference="ORD-TEST01", mirror=False)
            stock_service.move(shop, v.id, 2, "return", reference="ORD-TEST01", mirror=False)
        assert {ly.batch: ly.quantity for ly in plan.layers([shop.id])} == {"A": 2, "B": 1}

    def test_batches_heal_drift(self):
        from apps.stores.infrastructure.models import StockBatch

        shop, v = _store(), _variant()
        _put(shop, v, 4, batch_number="X", expiry_date=timezone.localdate() + timedelta(days=99))
        StoreProductStock.objects.filter(store=shop, product_variant_id=v.id).update(quantity=6)  # changed around move()
        with transaction.atomic():
            stock_service.move(shop, v.id, -1, "sale", mirror=False)
        assert sum(StockBatch.objects.filter(store=shop, product_variant_id=v.id).values_list("quantity", flat=True)) == 5

    def test_stock_without_expiry_is_reported_as_unknown(self):
        shop, v = _store(), _variant()
        _put(shop, v, 3)
        rep = plan.expiry_report([shop.id])
        assert rep["unknown_units"] == 3 and not rep["layers"]

    def test_page_and_excel(self):
        shop, v = _store(), _variant()
        _put(shop, v, 2, batch_number="B1", expiry_date=date.today() - timedelta(days=1))
        boss = _client(superuser=True)
        for url in ("/django-admin/wms/expiry/", f"/django-admin/wms/expiry/?location={shop.id}&tab=expired", "/django-admin/wms/expiry/?tab=all&q=B1",
                    "/django-admin/wms/expiry/?export=xlsx", f"/django-admin/wms/stock/?location={shop.id}"):
            assert boss.get(url).status_code == 200, url
        page = boss.get(f"/django-admin/wms/expiry/?location={shop.id}&tab=expired").content.decode()
        assert "LOT B1" in page and "writeoff/new/" in page


class TestReports:
    def test_turnover_abc_dead_stock_and_page(self):
        from apps.stores.infrastructure import report_service

        wh, shop, fast, slow, dead = _store("warehouse", "WH"), _store(), _variant(), _variant(), _variant()
        for v, cost in ((fast, "1000"), (slow, "1000"), (dead, "5000")):
            stock_service.post_receipt(shop, [{"variant_id": v.id, "quantity": 100, "unit_cost": cost}], "Ali")
        with transaction.atomic():
            stock_service.move(shop, fast.id, -90, "sale", reference="S1", mirror=False)
            stock_service.move(shop, slow.id, -5, "sale", reference="S2", mirror=False)
            stock_service.move(shop, slow.id, -2, "damage", reference="HC", mirror=False)
        rep = report_service.build([shop.id], 30)
        rows = {r.variant_id: r for r in rep["rows"]}
        assert rows[fast.id].abc == "A" and rows[slow.id].abc in ("B", "C") and rows[dead.id].dead
        assert rep["cogs"] == Decimal("95000") and rep["loss_units"] == 2 and rep["flow_in"]["receipt"]["units"] == 300
        assert rows[fast.id].cover == 3  # 10 left at 3 a day
        boss = _client(superuser=True)
        for url in ("/django-admin/wms/reports/", f"/django-admin/wms/reports/?location={shop.id}&days=90&tab=dead", "/django-admin/wms/reports/?tab=A",
                    "/django-admin/wms/reports/?export=xlsx"):
            assert boss.get(url).status_code == 200, url
