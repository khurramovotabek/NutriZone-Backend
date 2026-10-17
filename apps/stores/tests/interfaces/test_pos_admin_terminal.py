"""
Dashboard POS terminal = the ONLINE kassa (main warehouse stock, no branch to pick): open the shift with a note + the
kassa PIN (no float), sell (stock leaves through the ledger with the staff member as actor), split payment, close.
"""
from __future__ import annotations

import json
import uuid

import pytest
from django.contrib.auth.models import User as StaffUser
from django.db import transaction
from django.test import Client

from apps.pos.infrastructure.models import SaleModel
from apps.stores.infrastructure import stock_service
from apps.stores.infrastructure.models import CashSession, StockMovement, Store, StoreProductStock
from apps.stores.tests.interfaces.test_store_pos import _priced_variant

pytestmark = pytest.mark.django_db
API = "/django-admin/pos/terminal/api2/"


@pytest.fixture
def staff():
    client = Client()
    client.force_login(StaffUser.objects.create_superuser(username=f"pos_{uuid.uuid4().hex[:6]}", password="x-pass-12345", first_name="Kassir", last_name="Admin"))
    return client


@pytest.fixture
def kassa():
    from apps.stores.infrastructure import pos_cashiers

    wh = Store.objects.create(id=uuid.uuid4(), name="Asosiy sklad", slug=f"wh-{uuid.uuid4().hex[:6]}", kind="warehouse", status="active")
    v = _priced_variant("100000", "Whey Test")
    with transaction.atomic():
        stock_service.move(wh, v.id, 4, "receipt", reference="T", mirror=False)
    pos_cashiers.set_pin(wh, "4826")
    return wh, v


def post(c, action, **body):
    return c.post(f"{API}{action}", json.dumps(body), content_type="application/json")


def test_full_shift_and_sale(staff, kassa):
    wh, v = kassa
    page = staff.get("/django-admin/pos/terminal/", HTTP_ACCEPT_LANGUAGE="uz")
    assert page.status_code == 200 and b"Onlayn kassa" in page.content
    state = staff.get(f"{API}state").json()["data"]
    assert state["session"] is None and state["has_pin"] and state["store"]["name"] == "Onlayn kassa"
    wrong = post(staff, "open_shift", note="x", pin="1111")
    assert wrong.status_code == 409 and wrong.json()["error"]["code"] == "PIN_WRONG" and wrong.json()["error"]["details"]["left"] == 4
    opened = post(staff, "open_shift", note="Onlayn buyurtmalar", pin="4826").json()["data"]
    sale = opened["sale"]
    assert opened["session"]["status"] == "open" and opened["session"]["opening_cash"] == "0.00"
    assert opened["session"]["opened_by"] == "Kassir Admin" and opened["session"]["number"] == 1
    cat = staff.get(f"{API}catalog").json()["data"]
    assert cat["results"][0]["stock"] == 4
    sale = post(staff, "add", sale_id=sale["id"], variant_id=str(v.id), quantity=3).json()["data"]["sale"]
    assert sale["total"] == "300000.00" and sale["kassa"] == "Onlayn kassa"
    done = post(staff, "complete", sale_id=sale["id"], payment_method="cash", payments=[{"method": "cash", "amount": 100000}, {"method": "uzcard", "amount": 200000}], amount_tendered=150000).json()["data"]
    assert done["done"]["status"] == "completed" and done["done"]["change"] == "50000.00" and done["sale"]["id"] != sale["id"]
    assert done["done"]["cashier"] == "Kassir Admin"
    assert StoreProductStock.objects.get(store=wh, product_variant=v).quantity == 1
    m = StockMovement.objects.get(store=wh, movement_type="sale")
    assert m.quantity == -3 and m.actor == "Kassir Admin"
    totals = staff.get(f"{API}shift_totals").json()["data"]["session"]
    assert totals["sales_count"] == 1 and totals["expected_cash"] == "100000.00"  # no float: just the cash part
    closed = post(staff, "close_shift", counted_cash="100000").json()["data"]["session"]
    assert closed["status"] == "closed" and closed["cash_difference"] == "0.00" and closed["closed_by"] == "Kassir Admin"
    ses = CashSession.objects.get(store=wh)
    assert ses.opened_by_id is None and ses.opened_by_name == "Kassir Admin" and ses.opening_note == "Onlayn buyurtmalar"


def test_kassa_without_pin_or_warehouse_cannot_open(staff):
    assert staff.get(f"{API}state").status_code == 422  # no warehouse -> no online kassa
    wh = Store.objects.create(id=uuid.uuid4(), name="WH", slug=f"wh-{uuid.uuid4().hex[:6]}", kind="warehouse", status="active")
    assert staff.get(f"{API}state").json()["data"]["has_pin"] is False
    r = post(staff, "open_shift", pin="4826")
    assert r.json()["error"]["code"] == "KASSA_PIN_NOT_SET" and not CashSession.objects.filter(store=wh).exists()


def test_needs_pos_permission(kassa):
    c = Client()
    c.force_login(StaffUser.objects.create_user(username=f"np_{uuid.uuid4().hex[:6]}", password="x-pass-12345", is_staff=True))
    assert c.get(f"{API}state").status_code == 403
