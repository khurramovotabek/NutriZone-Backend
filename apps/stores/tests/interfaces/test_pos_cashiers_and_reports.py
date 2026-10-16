"""
Kassas and cashiers: one shared PIN per kassa (opens the shift, hands the terminal over, lockout), cashiers = customer
accounts linked to a kassa (My store → POS, sales recorded per cashier, owner-only pages closed to them), the
"Kassalar va kassirlar" admin page, e-receipt + Z-report on close, quick buttons, the receipt fields, leaderboards.
"""
from __future__ import annotations

import json
import uuid
from unittest import mock

import pytest
from django.contrib.auth.models import User as StaffUser
from django.db import transaction
from django.test import Client
from rest_framework.test import APIClient

from apps.notifications.infrastructure.models import NotificationModel
from apps.pos.infrastructure.models import SaleModel
from apps.stores.infrastructure import pos_cashiers, shift_report, stock_service
from apps.stores.infrastructure.models import CashSession, StockMovement, Store, StoreCashier
from apps.stores.tests.interfaces.test_my_store_products import _authenticate_as, _make_owner, _make_store
from apps.stores.tests.interfaces.test_store_pos import _priced_variant
from common.exceptions import DomainException

pytestmark = pytest.mark.django_db
POS = "/api/v1/my-store/pos/"


@pytest.fixture
def staff():
    client = Client()
    client.force_login(StaffUser.objects.create_superuser(username=f"pc_{uuid.uuid4().hex[:6]}", password="x-pass-12345", first_name="Bosh", last_name="Admin"))
    return client


@pytest.fixture
def kassa():
    owner = _make_owner(full_name="Olmazor Egasi")
    store = _make_store(owner, name="LifeSport Test")
    v = _priced_variant("50000", "Creatine T")
    with transaction.atomic():
        stock_service.move(store, v.id, 10, "receipt", reference="T", mirror=False)
    pos_cashiers.set_pin(store, "2707")
    aziza, bekzod = _make_owner(full_name="Aziza Karimova"), _make_owner(full_name="Bekzod Aliyev")
    for u in (aziza, bekzod):
        StoreCashier.objects.create(store=store, user=u)
    return {"store": store, "v": v, "owner": owner, "aziza": aziza, "bekzod": bekzod}


def _as(monkeypatch, user, token=None):
    _authenticate_as(monkeypatch, user)
    c = APIClient()
    if token:
        c.credentials(HTTP_X_POS_CASHIER=token)
    return c


def _sell(c, v, qty, cash):
    sale = c.post(f"{POS}sales/current", format="json").json()["data"]
    sale = c.post(f"{POS}sales/{sale['id']}/items", {"variant_id": str(v.id), "quantity": qty}, format="json").json()["data"]
    return c.post(f"{POS}sales/{sale['id']}/complete", {"payment_method": "cash", "amount_tendered": cash}, format="json").json()["data"]


def test_kassa_pin_rules_and_lockout(kassa):
    store = kassa["store"]
    for bad in ("12", "1111", "1234", "abcd", "1234567"):
        with pytest.raises(DomainException):
            pos_cashiers.valid_pin(bad)
    pos_cashiers.verify_pin(store, "2707")
    for left in (4, 3, 2, 1):
        with pytest.raises(DomainException) as e:
            pos_cashiers.verify_pin(store, "0000")
        assert e.value.code == "PIN_WRONG" and e.value.details["left"] == left
    with pytest.raises(DomainException) as e:
        pos_cashiers.verify_pin(store, "0000")
    assert e.value.code == "PIN_LOCKED"
    with pytest.raises(DomainException) as e:  # even the right PIN waits out the lock
        pos_cashiers.verify_pin(store, "2707")
    assert e.value.code == "PIN_LOCKED"
    other = _make_store(_make_owner())
    with pytest.raises(DomainException) as e:
        pos_cashiers.verify_pin(other, "2707")
    assert e.value.code == "KASSA_PIN_NOT_SET"


def test_cashiers_share_one_kassa_and_every_sale_is_theirs(monkeypatch, kassa, django_capture_on_commit_callbacks):
    store, v, aziza, bekzod = kassa["store"], kassa["v"], kassa["aziza"], kassa["bekzod"]
    c = _as(monkeypatch, aziza)
    me = c.get("/api/v1/my-store").json()["data"]
    assert me["my_role"] == "cashier" and me["name"] == "LifeSport Test"
    cfg = c.get(f"{POS}config").json()["data"]
    assert cfg["role"] == "cashier" and cfg["kassa"]["has_pin"] and cfg["cashier"]["full_name"] == "Aziza Karimova"
    assert [p["full_name"] for p in cfg["cashiers"]] == ["Olmazor Egasi", "Aziza Karimova", "Bekzod Aliyev"]
    assert c.post(f"{POS}session/open", {"note": "ertalab"}, format="json").json()["error"]["code"] == "PIN_WRONG"
    opened = c.post(f"{POS}session/open", {"note": "ertalab", "pin": "2707"}, format="json").json()["data"]
    assert opened["opened_by"] == "Aziza Karimova" and opened["opening_cash"] == "0.00" and opened["opening_note"] == "ertalab"
    first = _sell(c, v, 2, 100000)
    assert first["cashier"] == "Aziza Karimova" and first["kassa"] == "LifeSport Test"

    # hand the same computer to Bekzod with the kassa PIN
    assert c.post(f"{POS}cashier", {"cashier_id": str(bekzod.id), "pin": "1111"}, format="json").status_code == 409
    switched = c.post(f"{POS}cashier", {"cashier_id": str(bekzod.id), "pin": "2707"}, format="json").json()["data"]
    assert switched["cashier"]["full_name"] == "Bekzod Aliyev"
    c2 = _as(monkeypatch, aziza, switched["token"])
    assert c2.get(f"{POS}config").json()["data"]["cashier"]["full_name"] == "Bekzod Aliyev"
    second = _sell(c2, v, 1, 50000)
    assert second["cashier"] == "Bekzod Aliyev"

    done = SaleModel.objects.filter(branch_id=store.id, status="completed")
    assert set(done.values_list("cashier_id", flat=True)) == {aziza.id, bekzod.id}
    assert set(StockMovement.objects.filter(store=store, movement_type="sale").values_list("actor", flat=True)) == {"Aziza Karimova", "Bekzod Aliyev"}

    # cashiers sell; owner-only pages stay closed
    assert c.get(f"{POS}analytics").status_code == 403
    assert c.patch("/api/v1/my-store", {"description": "x"}, format="json").status_code == 404
    with django_capture_on_commit_callbacks(execute=True):
        z = c2.post(f"{POS}session/close", {"counted_cash": "150000"}, format="json").json()["data"]
    assert z["closed_by"] == "Bekzod Aliyev" and z["cash_difference"] == "0.00"
    text = shift_report.report_text(CashSession.objects.select_related("store").get(store=store))
    assert "Aziza Karimova: 1 ta · 100 000" in text and "Bekzod Aliyev: 1 ta · 50 000" in text and "smena №1" in text and "Ochdi: Aziza Karimova" in text


def test_a_hand_over_token_only_works_at_its_own_kassa(monkeypatch, kassa):
    other_owner = _make_owner(full_name="Boshqa Ega")
    other = _make_store(other_owner)
    pos_cashiers.set_pin(other, "4826")
    token = pos_cashiers.issue_token(kassa["store"], kassa["aziza"].id)
    assert pos_cashiers.cashier_from_token(kassa["store"], token) == kassa["aziza"].id
    assert pos_cashiers.cashier_from_token(other, token) is None
    assert pos_cashiers.cashier_from_token(kassa["store"], token + "x") is None
    c = _as(monkeypatch, other_owner, token)  # someone else's token is ignored: the owner sells as themself
    assert c.get(f"{POS}config").json()["data"]["cashier"]["full_name"] == "Boshqa Ega"
    StoreCashier.objects.filter(user=kassa["aziza"]).update(is_active=False)  # removed cashier -> token dies
    assert pos_cashiers.cashier_from_token(kassa["store"], token) is None
    assert c.post(f"{POS}cashier", {"cashier_id": str(kassa["bekzod"].id), "pin": "4826"}, format="json").json()["error"]["code"] == "CASHIER_NOT_ALLOWED"


def test_receipt_fields_customer_e_receipt_and_z_report(monkeypatch, kassa, django_capture_on_commit_callbacks, settings):
    from apps.identity.infrastructure.models import User
    from apps.pos.infrastructure import receipts

    settings.TELEGRAM_ORDERS_CHAT_ID = "-100123"
    store, v = kassa["store"], kassa["v"]
    buyer = User.objects.create(phone_number=f"+99891{uuid.uuid4().int % 10**7:07d}", full_name="Mijoz Test")
    c = _as(monkeypatch, kassa["aziza"])
    c.post(f"{POS}session/open", {"pin": "2707"}, format="json")
    sale = c.post(f"{POS}sales/current", format="json").json()["data"]
    c.post(f"{POS}sales/{sale['id']}/items", {"variant_id": str(v.id), "quantity": 1}, format="json")
    c.post(f"{POS}sales/{sale['id']}/customer", {"customer_id": str(buyer.id)}, format="json")
    with django_capture_on_commit_callbacks(execute=True):
        c.post(f"{POS}sales/{sale['id']}/complete", {"payment_method": "cash", "amount_tendered": 50000}, format="json")
    assert NotificationModel.objects.get(recipient_id=buyer.id, kind="pos_receipt").link.startswith("/r/")
    rc = receipts.receipt(SaleModel.objects.get(id=sale["id"]))
    assert rc["cashier"] == "Aziza Karimova" and rc["kassa"] == "LifeSport Test" and rc["shift"] == 1 and rc["customer"]["name"] == "Mijoz"
    gateway = mock.Mock()
    with mock.patch("apps.notifications.infrastructure.composition.build_orders_telegram_gateway", return_value=gateway), django_capture_on_commit_callbacks(execute=True):
        assert c.post(f"{POS}session/close", {"counted_cash": "50000"}, format="json").status_code == 200
    assert NotificationModel.objects.filter(recipient_id=store.owner_id, kind="shift_closed").exists()
    chat, text, _kb = gateway.send_message_with_keyboard.call_args.args
    assert chat == "-100123" and "Z-hisobot · LifeSport Test" in text and "Savdolar: <b>1</b>" in text


def test_quick_buttons_thermal_receipt_and_leaderboard(monkeypatch, staff, kassa):
    store, v = kassa["store"], kassa["v"]
    c = _as(monkeypatch, kassa["owner"])
    c.post(f"{POS}session/open", {"pin": "2707"}, format="json")
    done = _sell(c, v, 3, 150000)
    top = c.get(f"{POS}top").json()["data"]["results"]
    assert top and top[0]["variant_id"] == str(v.id) and top[0]["sellable"] and top[0]["sold"] == 3
    slip = staff.get(f"/django-admin/pos/terminal/receipt/{done['id']}/?w=58").content.decode()
    assert done["number"] in slip and "58mm" in slip and "Creatine T" in slip and "Olmazor Egasi" in slip and "smena" in slip.lower()
    from apps.platform.infrastructure.dashboard_rankings import build

    r = build(7)
    assert any(p["name"] == "Creatine T" and p["units"] >= 3 for p in r["products"])
    assert any(b["name"] == store.name for b in r["branches"]) and any(x["name"] == "Olmazor Egasi" for x in r["cashiers"])


def test_kassalar_page_sets_pins_and_links_cashiers(staff, kassa, django_capture_on_commit_callbacks):
    store = kassa["store"]
    page = staff.get("/django-admin/stores/storecashier/")
    html = page.content.decode()
    assert page.status_code == 200 and "LifeSport Test" in html and "Aziza Karimova" in html and "Olmazor Egasi" in html

    assert staff.post(f"/django-admin/stores/storecashier/pin/{store.id}/", {"pin": "5821", "pin_again": "5822"}).status_code == 302
    pos_cashiers.verify_pin(Store.objects.get(id=store.id), "2707")  # mismatch -> unchanged
    staff.post(f"/django-admin/stores/storecashier/pin/{store.id}/", {"pin": "5821", "pin_again": "5821"})
    pos_cashiers.verify_pin(Store.objects.get(id=store.id), "5821")

    new = _make_owner(full_name="Dilnoza Yangi")
    found = staff.get("/django-admin/stores/storecashier/users/?q=Dilnoza").json()["results"]
    assert found[0]["id"] == str(new.id) and found[0]["works_at"] is None
    with django_capture_on_commit_callbacks(execute=True):
        staff.post("/django-admin/stores/storecashier/link/", {"store": str(store.id), "user": str(new.id)})
    link = StoreCashier.objects.get(user=new)
    assert link.store_id == store.id and link.added_by == "Bosh Admin"
    assert NotificationModel.objects.filter(recipient_id=new.id, kind="cashier_added").exists()
    assert pos_cashiers.store_for_user(new.id) == (store, "cashier")

    other_owner = _make_owner()
    _make_store(other_owner)
    staff.post("/django-admin/stores/storecashier/link/", {"store": str(store.id), "user": str(other_owner.id)})
    assert not StoreCashier.objects.filter(user=other_owner).exists()  # an owner can't be a cashier elsewhere

    staff.post(f"/django-admin/stores/storecashier/unlink/{link.id}/")
    assert not StoreCashier.objects.filter(user=new).exists() and pos_cashiers.store_for_user(new.id) == (None, None)
    assert staff.get(f"/django-admin/stores/storecashier/unlink/{kassa['aziza'].cashier_link.id}/").status_code == 403  # POST only


def test_branch_receipts_list_with_today_totals_and_masked_phones(monkeypatch, kassa):
    from apps.receipts.infrastructure import builders

    mine = builders.manual(lines=[{"name": "Whey", "quantity": 2, "unit_price": "1000"}], customer_name="Aziz", customer_phone="+998901234567")
    mine.store_id = kassa["store"].id
    mine.save(update_fields=["store_id"])
    builders.manual(lines=[{"name": "Elsewhere", "quantity": 1, "unit_price": "5000"}])  # another branch / no branch
    data = _as(monkeypatch, kassa["aziza"]).get("/api/v1/my-store/receipts?days=1").json()["data"]  # cashiers see them too
    assert [r["number"] for r in data["receipts"]] == [mine.number]
    assert data["receipts"][0]["phone"] == "+99890***67" and data["today"]["sales"] == 1 and data["today"]["revenue"] == "2000.00"
    assert _as(monkeypatch, kassa["owner"]).get("/api/v1/my-store/receipts?q=4567").json()["data"]["receipts"][0]["number"] == mine.number
