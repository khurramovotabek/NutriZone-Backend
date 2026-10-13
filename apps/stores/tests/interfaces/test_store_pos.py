"""Store POS terminal: server-side prices, store stock limits, payment, refunds, cross-store isolation, reports."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.pos.infrastructure.models import SaleModel
from apps.products.infrastructure.models import ProductTranslation
from apps.stores.infrastructure.models import StoreProductStock
from apps.stores.tests.interfaces.test_my_store_products import _authenticate_as, _make_owner, _make_store, _make_variant

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _priced_variant(price="120000", name="Whey Gold", **kw):
    from apps.pricing.infrastructure import models as pricing_orm

    variant = _make_variant(**kw)
    ProductTranslation.objects.create(product=variant.product, locale_code="uz", name=name, slug=f"s-{uuid.uuid4().hex[:8]}")
    price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
    pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant.id, base_price_amount=Decimal(price))
    return variant


@pytest.fixture
def shop(monkeypatch):
    owner = _make_owner()
    store = _make_store(owner)
    whey = _priced_variant("120000", "Whey Gold", barcode="4780000000017")
    creatine = _priced_variant("80000", "Creatine")
    StoreProductStock.objects.create(store=store, product_variant=whey, quantity=5)
    StoreProductStock.objects.create(store=store, product_variant=creatine, quantity=2)
    from apps.stores.infrastructure import pos_cashiers

    pos_cashiers.set_pin(store, "2707")  # one shared PIN per kassa; opening a shift asks for it (no opening float)
    _authenticate_as(monkeypatch, owner)
    client = APIClient()
    assert client.post("/api/v1/my-store/pos/session/open", {"pin": "2707", "note": "ertalabki smena"}, format="json").status_code == 201
    return {"client": client, "owner": owner, "store": store, "whey": whey, "creatine": creatine}


def _open(c):
    return c.post("/api/v1/my-store/pos/sales/current", format="json").json()["data"]


def _add(c, sale_id, variant, qty=1):
    return c.post(f"/api/v1/my-store/pos/sales/{sale_id}/items", {"variant_id": str(variant.id), "quantity": qty}, format="json")


def test_catalog_lists_only_my_stock_with_live_prices_and_barcode_match(shop):
    data = shop["client"].get("/api/v1/my-store/pos/catalog?q=4780000000017").json()["data"]
    assert data["exact_match"]["name"] == "Whey Gold"
    assert data["exact_match"]["price"] == "120000.00" and data["exact_match"]["stock"] == 5


def test_full_cash_sale_decrements_store_stock_and_records_change(shop):
    c = shop["client"]
    sale = _open(c)
    assert _open(c)["id"] == sale["id"]  # resumes the same open basket
    _add(c, sale["id"], shop["whey"], 2)
    body = _add(c, sale["id"], shop["whey"], 1).json()["data"]  # tops up the same line
    assert len(body["items"]) == 1 and body["items"][0]["quantity"] == 3
    assert body["total"] == "360000.00"

    r = c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/complete", {"payment_method": "cash", "amount_tendered": "400000"}, format="json")
    assert r.status_code == 200, r.json()
    done = r.json()["data"]
    assert done["status"] == "completed" and done["change"] == "40000.00" and done["payment_method"] == "cash"
    assert StoreProductStock.objects.get(store=shop["store"], product_variant=shop["whey"]).quantity == 2
    assert SaleModel.objects.get(id=sale["id"]).channel == "store"


def test_cannot_sell_more_than_store_holds(shop):
    c = shop["client"]
    sale = _open(c)
    r = _add(c, sale["id"], shop["creatine"], 3)
    assert r.status_code == 409


def test_client_cannot_set_price(shop):
    c = shop["client"]
    sale = _open(c)
    c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/items", {"variant_id": str(shop["creatine"].id), "quantity": 1, "unit_price_amount": "1"}, format="json")
    assert c.get(f"/api/v1/my-store/pos/sales/{sale['id']}").json()["data"]["total"] == "80000.00"


def test_cash_below_total_and_non_live_methods_are_rejected(shop):
    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["creatine"], 1)
    low = c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/complete", {"payment_method": "cash", "amount_tendered": "50000"}, format="json")
    card = c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/complete", {"payment_method": "card"}, format="json")
    assert low.status_code == 409 and card.status_code == 409
    assert StoreProductStock.objects.get(store=shop["store"], product_variant=shop["creatine"]).quantity == 2


def test_stock_sold_elsewhere_between_add_and_pay_blocks_completion(shop):
    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["creatine"], 2)
    StoreProductStock.objects.filter(store=shop["store"], product_variant=shop["creatine"]).update(quantity=1)
    r = c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/complete", {"payment_method": "cash", "amount_tendered": "200000"}, format="json")
    assert r.status_code == 409
    assert SaleModel.objects.get(id=sale["id"]).status == "open"


def test_refund_returns_units_to_the_shelf(shop):
    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["whey"], 2)
    c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/complete", {"payment_method": "cash", "amount_tendered": "240000"}, format="json")
    r = c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/refund", format="json")
    assert r.json()["data"]["status"] == "refunded"
    assert StoreProductStock.objects.get(store=shop["store"], product_variant=shop["whey"]).quantity == 5


def test_customer_by_phone_is_found_or_created(shop):
    c = shop["client"]
    sale = _open(c)
    need_name = c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/customer", {"phone_number": "+998901112233"}, format="json")
    assert need_name.status_code == 422
    ok = c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/customer", {"phone_number": "+998901112233", "full_name": "Ali Karimov"}, format="json")
    assert ok.json()["data"]["customer"]["full_name"] == "Ali Karimov"


def test_another_owner_cannot_touch_my_sale(shop, monkeypatch):
    sale = _open(shop["client"])
    intruder = _make_owner()
    _make_store(intruder)
    _authenticate_as(monkeypatch, intruder)
    other = APIClient()
    assert other.get(f"/api/v1/my-store/pos/sales/{sale['id']}").status_code == 404
    assert _add(other, sale["id"], shop["whey"]).status_code == 404


def test_history_summary(shop):
    c = shop["client"]
    for qty in (1, 2):
        sale = _open(c)
        _add(c, sale["id"], shop["whey"], qty)
        c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/complete", {"payment_method": "cash", "amount_tendered": "1000000"}, format="json")
    data = c.get("/api/v1/my-store/pos/analytics?period=today").json()["data"]
    assert data["kpis"]["sales_count"] == 2
    assert data["kpis"]["revenue"] == "360000.00"
    assert data["kpis"]["items_sold"] == 3
    assert data["top_products"][0]["name"] == "Whey Gold"
    assert len(c.get("/api/v1/my-store/pos/sales?period=today").json()["data"]["results"]) == 2


# ---------------------------------------------------------------- shifts


def _pay(c, sale_id, tendered="10000000", coins=0):
    return c.post(f"/api/v1/my-store/pos/sales/{sale_id}/complete", {"payment_method": "cash", "amount_tendered": tendered, "coins": coins}, format="json")


def test_selling_requires_an_open_register(monkeypatch):
    owner = _make_owner()
    _make_store(owner)
    _authenticate_as(monkeypatch, owner)
    r = APIClient().post("/api/v1/my-store/pos/sales/current", format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "REGISTER_CLOSED"


def test_register_cannot_be_opened_twice(shop):
    r = shop["client"].post("/api/v1/my-store/pos/session/open", {"pin": "2707"}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "REGISTER_ALREADY_OPEN"


def test_close_register_produces_exact_z_report(shop):
    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["whey"], 2)  # 240 000
    _pay(c, sale["id"], "250000")
    other = _open(c)
    _add(c, other["id"], shop["creatine"], 1)  # 80 000
    _pay(c, other["id"], "80000")
    c.post(f"/api/v1/my-store/pos/sales/{other['id']}/refund", format="json")

    z = c.post("/api/v1/my-store/pos/session/close", {"counted_cash": "235000"}, format="json").json()["data"]
    assert z["status"] == "closed"
    assert z["sales_count"] == 2 and z["gross_sales"] == "320000.00" and z["refunds_count"] == 1
    assert z["expected_cash"] == "240000.00"  # no float: 320 000 taken − 80 000 refunded
    assert z["cash_difference"] == "-5000.00"
    assert c.post("/api/v1/my-store/pos/sales/current", format="json").status_code == 409  # closed → no selling
    assert len(c.get("/api/v1/my-store/pos/sessions").json()["data"]["results"]) == 1


def test_cannot_close_with_items_in_basket(shop):
    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["whey"], 1)
    r = c.post("/api/v1/my-store/pos/session/close", {"counted_cash": "100000"}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "OPEN_BASKET"


# ---------------------------------------------------------------- customers & coins


def test_customer_search_respects_privacy(shop):
    from apps.identity.infrastructure.models import User

    stranger = User.objects.create(phone_number="+998935550011", full_name="Begona Mijoz", status="active")
    c = shop["client"]
    assert c.get("/api/v1/my-store/pos/customers?q=Begona").json()["data"] == []  # not our buyer → not browsable
    exact = c.get("/api/v1/my-store/pos/customers?q=%2B998935550011").json()["data"]
    assert [x["id"] for x in exact] == [str(stranger.id)]  # exact phone works
    assert "balance" in exact[0]


def test_paying_with_coins_and_earning_cashback(shop, django_capture_on_commit_callbacks):
    from unittest import mock

    from apps.identity.infrastructure.models import User
    from apps.loyalty.infrastructure import notifications, services
    from apps.loyalty.infrastructure.models import Wallet, WalletTransaction

    buyer = User.objects.create(phone_number="+998935550022", full_name="Coin Buyer", status="active")
    services.adjust(buyer.id, 50_000, "gift")
    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["whey"], 1)  # 120 000
    data = c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/customer", {"customer_id": str(buyer.id)}, format="json").json()["data"]
    assert data["customer"]["balance"] == 50_000 and data["customer"]["redeem"]["max_coins"] == 36_000  # 30% cap

    too_many = _pay(c, sale["id"], coins=40_000)
    assert too_many.status_code == 409 and too_many.json()["error"]["code"] == "REDEEM_ABOVE_LIMIT"
    short = _pay(c, sale["id"], tendered="50000", coins=36_000)  # due 84 000
    assert short.json()["error"]["code"] == "CASH_TENDERED_TOO_LOW"

    with mock.patch.object(notifications, "queue"), django_capture_on_commit_callbacks(execute=True):
        done = _pay(c, sale["id"], tendered="100000", coins=36_000).json()["data"]
    assert done["coins_redeemed"] == "36000.00" and done["amount_due"] == "84000.00" and done["change"] == "16000.00"
    earn = WalletTransaction.objects.get(order_id=sale["id"], kind="earn")
    assert earn.amount == 840  # bronze 1% of the 84 000 actually paid
    assert Wallet.objects.get(user_id=buyer.id).balance == 50_000 - 36_000 + 840

    # refund: coins come back, cashback is taken back
    c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/refund", format="json")
    assert Wallet.objects.get(user_id=buyer.id).balance == 50_000


def test_coins_need_a_customer(shop):
    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["whey"], 1)
    r = _pay(c, sale["id"], coins=5_000)
    assert r.json()["error"]["code"] == "COINS_NEED_CUSTOMER"


# ---------------------------------------------------------------- reports


def test_stock_view_and_analytics(shop):
    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["whey"], 4)
    _pay(c, sale["id"])
    stock = c.get("/api/v1/my-store/pos/stock").json()["data"]
    assert stock["summary"]["low"] == 2  # whey 1 left, creatine 2 left (threshold 5)
    assert stock["attention"][0]["stock"] == 1
    assert c.get("/api/v1/my-store/pos/stock?q=creat").json()["data"]["results"][0]["name"] == "Creatine"

    a = c.get("/api/v1/my-store/pos/analytics?period=7d").json()["data"]
    assert a["kpis"]["revenue"] == "480000.00" and len(a["series"]) == 7
    h = c.get("/api/v1/my-store/pos/sales?period=today").json()["data"]
    assert h["results"][0]["items"][0]["name"] == "Whey Gold" and h["results"][0]["items"][0]["quantity"] == 4


def test_park_and_resume_baskets(shop):
    c = shop["client"]
    first = _open(c)
    assert c.post(f"/api/v1/my-store/pos/sales/{first['id']}/park", {}, format="json").status_code == 422  # empty basket
    _add(c, first["id"], shop["whey"], 2)
    fresh = c.post(f"/api/v1/my-store/pos/sales/{first['id']}/park", {"label": "Ko'k kurtka"}, format="json").json()["data"]
    assert fresh["id"] != first["id"] and fresh["items"] == [] and _open(c)["id"] == fresh["id"]
    held = c.get("/api/v1/my-store/pos/sales/parked").json()["data"]["results"]
    assert [(h["id"], h["label"], h["items"], h["total"]) for h in held] == [(first["id"], "Ko'k kurtka", 2, "240000.00")]

    _add(c, fresh["id"], shop["creatine"], 1)
    back = c.post(f"/api/v1/my-store/pos/sales/{first['id']}/resume", format="json").json()["data"]
    assert back["id"] == first["id"] and back["items"][0]["quantity"] == 2
    held = c.get("/api/v1/my-store/pos/sales/parked").json()["data"]["results"]
    assert [h["id"] for h in held] == [fresh["id"]]  # the basket in progress took its place on hold
    assert c.post(f"/api/v1/my-store/pos/sales/{first['id']}/resume", format="json").status_code == 404
    # a held basket with items still blocks closing the shift
    c.delete(f"/api/v1/my-store/pos/sales/{first['id']}/items")
    assert c.post("/api/v1/my-store/pos/session/close", {"counted_cash": "0"}, format="json").status_code == 409
