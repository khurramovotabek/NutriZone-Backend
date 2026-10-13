"""Store POS, production hardening: receipt numbers + public e-receipt, idempotent checkout, Uzcard/Humo, discounts, dashboard refunds, manual tiers."""
from __future__ import annotations

import re
from decimal import Decimal

import pytest

from apps.pos.infrastructure.models import SaleModel
from apps.stores.infrastructure.models import StoreProductStock
from apps.stores.tests.interfaces.test_store_pos import _add, _open, shop  # noqa: F401 - pytest fixture

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _complete(c, sale_id, **body):
    return c.post(f"/api/v1/my-store/pos/sales/{sale_id}/complete", {"payment_method": "cash", **body}, format="json")


def test_completed_sale_gets_a_receipt_number_and_a_public_e_receipt(shop):
    from apps.identity.infrastructure.models import User

    c = shop["client"]
    buyer = User.objects.create(phone_number="+998935551234", full_name="Aziz Karimov", status="active")
    sale = _open(c)
    _add(c, sale["id"], shop["whey"], 1)
    c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/customer", {"customer_id": str(buyer.id)}, format="json")
    done = _complete(c, sale["id"], amount_tendered="120000").json()["data"]
    assert re.fullmatch(r"NZ-\d{6}", done["receipt_number"]) and done["number"] == done["receipt_number"]
    assert done["receipt_token"] and len(done["receipt_token"]) >= 16

    public = c.get(f"/api/v1/receipts/{done['receipt_token']}").json()["data"]
    assert public["number"] == done["receipt_number"] and public["total"] == "120000.00"
    assert public["seller"]["name"] == shop["store"].name
    assert public["customer"] == {"name": "Aziz", "phone": "+998 ** *** 12 34"}  # never the full name/phone publicly
    assert c.get("/api/v1/receipts/not-a-real-token-123").status_code == 404

    second = _open(c)
    _add(c, second["id"], shop["creatine"], 1)
    nxt = _complete(c, second["id"], amount_tendered="80000").json()["data"]["receipt_number"]
    assert int(nxt[3:]) == int(done["receipt_number"][3:]) + 1


def test_completing_twice_is_idempotent(shop):
    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["whey"], 2)
    first = _complete(c, sale["id"], amount_tendered="240000")
    again = _complete(c, sale["id"], amount_tendered="240000")
    assert first.status_code == 200 and again.status_code == 200
    assert again.json()["data"]["receipt_number"] == first.json()["data"]["receipt_number"]
    assert StoreProductStock.objects.get(store=shop["store"], product_variant=shop["whey"]).quantity == 3  # decremented once


def test_uzcard_takes_exactly_the_amount_due_and_stays_out_of_the_drawer(shop):
    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["whey"], 1)
    done = _complete(c, sale["id"], payment_method="uzcard", amount_tendered="999999").json()["data"]
    assert done["payment_method"] == "uzcard" and done["amount_tendered"] == "120000.00" and done["change"] == "0.00"
    other = _open(c)
    _add(c, other["id"], shop["creatine"], 1)
    _complete(c, other["id"], payment_method="humo")
    session = c.get("/api/v1/my-store/pos/session").json()["data"]
    assert session["uzcard_sales"] == "120000.00" and session["humo_sales"] == "80000.00" and session["cash_sales"] == "0"
    assert session["expected_cash"] == "0.00"  # no float, and card money is in the bank


def test_discount_is_capped_and_needs_a_reason(shop):
    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["whey"], 1)  # 120 000, cap 20% = 24 000
    too_much = _complete(c, sale["id"], discount="30000", discount_reason="friend")
    assert too_much.status_code == 409 and too_much.json()["error"]["code"] == "DISCOUNT_TOO_HIGH"
    no_reason = _complete(c, sale["id"], discount="10000")
    assert no_reason.status_code == 422
    done = _complete(c, sale["id"], discount="10000", discount_reason="Doimiy mijoz", amount_tendered="110000").json()["data"]
    assert done["discount"] == "10000.00" and done["amount_due"] == "110000.00" and done["change"] == "0.00"
    session = c.get("/api/v1/my-store/pos/session").json()["data"]
    assert session["discounts_total"] == "10000.00" and session["cash_sales"] == "110000.00"


def test_dashboard_refund_of_a_store_sale_restocks_that_store(shop):
    from apps.stores.infrastructure import pos_service

    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["creatine"], 2)
    _complete(c, sale["id"], amount_tendered="160000")
    assert StoreProductStock.objects.get(store=shop["store"], product_variant=shop["creatine"]).quantity == 0
    pos_service.refund(shop["store"], shop["owner"].id, sale["id"], require_session=False)
    assert SaleModel.objects.get(id=sale["id"]).status == "refunded"
    assert StoreProductStock.objects.get(store=shop["store"], product_variant=shop["creatine"]).quantity == 2


def test_manual_tier_sets_the_cashback_rate_and_is_logged(shop, django_capture_on_commit_callbacks):
    from unittest import mock

    from apps.identity.infrastructure.models import User
    from apps.loyalty.infrastructure import notifications, services
    from apps.loyalty.infrastructure.models import LoyaltyTier, TierChange, WalletTransaction

    buyer = User.objects.create(phone_number="+998935557788", full_name="VIP Guest", status="active")
    vip = LoyaltyTier.objects.order_by("-min_spend").first()
    change = services.set_tier(buyer.id, vip, "Partner", "superadmin")
    assert change.kind == "manual" and change.to_tier == vip.name and change.actor == "superadmin"
    assert services.summary(buyer.id).current_tier == vip and services.summary(buyer.id).manual

    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["whey"], 1)
    c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/customer", {"customer_id": str(buyer.id)}, format="json")
    with mock.patch.object(notifications, "queue"), django_capture_on_commit_callbacks(execute=True):
        _complete(c, sale["id"], amount_tendered="120000")
    earn = WalletTransaction.objects.get(order_id=sale["id"], kind="earn")
    assert earn.amount == int(Decimal("120000") * vip.percent / 100)

    services.set_tier(buyer.id, None, "back to normal", "superadmin")
    assert not services.summary(buyer.id).manual
    assert TierChange.objects.filter(wallet__user_id=buyer.id).count() == 2


def test_coin_adjustment_records_who_did_it(shop):
    from apps.identity.infrastructure.models import User
    from apps.loyalty.infrastructure import services

    buyer = User.objects.create(phone_number="+998935557799", full_name="Adjusted", status="active")
    tx = services.adjust(buyer.id, 5_000, "compensation", actor="superadmin")
    assert tx.actor == "superadmin" and tx.note == "compensation"


def test_sales_report_splits_revenue_by_payment_method(shop):
    from apps.pos.infrastructure import sales_reports as rep

    c = shop["client"]
    a = _open(c)
    _add(c, a["id"], shop["whey"], 1)
    _complete(c, a["id"], amount_tendered="120000")
    b = _open(c)
    _add(c, b["id"], shop["creatine"], 1)
    _complete(c, b["id"], payment_method="uzcard", discount="8000", discount_reason="promo")
    summary = rep.summary(rep.rows(rep.closed_sales()))
    assert summary["count"] == 2 and summary["revenue"] == Decimal("192000")
    assert summary["by_method"]["cash"] == Decimal("120000") and summary["by_method"]["uzcard"] == Decimal("72000") and summary["discount"] == Decimal("8000")
    branch = rep.by_branch(rep.rows(rep.closed_sales()))
    assert branch[0]["name"] == shop["store"].name and branch[0]["count"] == 2


# ---------------------------------------------------------------- split payments & partial returns


def test_split_payment_part_cash_part_uzcard(shop):
    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["whey"], 1)  # 120 000
    wrong = _complete(c, sale["id"], payments=[{"method": "cash", "amount": "50000"}, {"method": "uzcard", "amount": "60000"}])
    assert wrong.status_code == 409 and wrong.json()["error"]["code"] == "PAYMENT_SPLIT_MISMATCH"
    done = _complete(c, sale["id"], amount_tendered="60000", payments=[{"method": "cash", "amount": "50000"}, {"method": "uzcard", "amount": "70000"}]).json()["data"]
    assert done["payment_method"] == "mixed" and done["change"] == "10000.00"
    assert {p["method"]: p["amount"] for p in done["payments"]} == {"cash": "50000.00", "uzcard": "70000.00"}
    session = c.get("/api/v1/my-store/pos/session").json()["data"]
    assert session["cash_sales"] == "50000.00" and session["uzcard_sales"] == "70000.00"
    assert session["expected_cash"] == "50000.00"  # only the cash part (no float)


def test_partial_returns_add_up_exactly_to_the_whole_sale(shop, django_capture_on_commit_callbacks):
    from unittest import mock

    from apps.identity.infrastructure.models import User
    from apps.loyalty.infrastructure import notifications, services
    from apps.loyalty.infrastructure.models import Wallet

    StoreProductStock.objects.filter(store=shop["store"], product_variant=shop["whey"]).update(quantity=5)
    buyer = User.objects.create(phone_number="+998935556611", full_name="Split Buyer", status="active")
    services.adjust(buyer.id, 50_000, "gift")
    c = shop["client"]
    sale = _open(c)
    data = _add(c, sale["id"], shop["whey"], 3).json()["data"]  # 360 000
    line_id = data["items"][0]["id"]
    c.post(f"/api/v1/my-store/pos/sales/{sale['id']}/customer", {"customer_id": str(buyer.id)}, format="json")
    with mock.patch.object(notifications, "queue"), django_capture_on_commit_callbacks(execute=True):
        # 360 000 − 36 000 discount − 30 000 coins = 294 000 = 94 000 cash + 200 000 Uzcard; cashback 1% = 2 940
        _complete(c, sale["id"], discount="36000", discount_reason="bulk", coins=30000, amount_tendered="94000",
                  payments=[{"method": "cash", "amount": "94000"}, {"method": "uzcard", "amount": "200000"}])
    assert Wallet.objects.get(user_id=buyer.id).balance == 50_000 - 30_000 + 2_940

    url = f"/api/v1/my-store/pos/sales/{sale['id']}/refund"
    preview = c.post(url, {"items": [{"line_id": line_id, "quantity": 1}], "preview": True}, format="json").json()["data"]["preview"]
    assert preview["value"] == "108000" and preview["coins"] == "10000" and preview["amount"] == "98000"
    assert preview["split"] == {"cash": "31333", "uzcard": "66667"} and preview["cashback"] == 980 and not preview["final"]
    assert SaleModel.objects.get(id=sale["id"]).refunded_amount == 0  # preview changes nothing

    first = c.post(url, {"items": [{"line_id": line_id, "quantity": 1}], "reason": "damaged"}, format="json").json()["data"]
    assert first["status"] == "completed" and first["items"][0]["refunded_quantity"] == 1 and first["refunds"][0]["number"].endswith("-R1")
    too_many = c.post(url, {"items": [{"line_id": line_id, "quantity": 3}]}, format="json")
    assert too_many.status_code == 409 and too_many.json()["error"]["code"] == "RETURN_QTY_TOO_HIGH"

    last = c.post(url, {}, format="json").json()["data"]  # everything left
    assert last["status"] == "refunded" and last["refund"]["final"]
    assert last["refund"]["value"] == "216000.00" and last["refund"]["split"] == {"cash": "62667.00", "uzcard": "133333.00"}
    row = SaleModel.objects.get(id=sale["id"])
    assert row.refunded_amount == Decimal("294000") and row.refunded_coins == Decimal("30000")
    assert StoreProductStock.objects.get(store=shop["store"], product_variant=shop["whey"]).quantity == 5
    assert Wallet.objects.get(user_id=buyer.id).balance == 50_000  # coins back, all cashback taken back
    session = c.get("/api/v1/my-store/pos/session").json()["data"]
    assert session["refunds_count"] == 2 and session["cash_refunded"] == "94000.00" and session["expected_cash"] == "0.00"


# ---------------------------------------------------------------- dashboard: store colours & daily sales by store


def test_every_new_store_gets_its_own_lifelong_colour(shop):
    from apps.stores.infrastructure.models import Store
    from apps.stores.tests.interfaces.test_my_store_products import _make_owner, _make_store

    other = _make_store(_make_owner())
    colours = list(Store.objects.values_list("color", flat=True))
    assert all(re.fullmatch(r"#[0-9A-Fa-f]{6}", c) for c in colours) and len(set(colours)) == len(colours)
    other.name = "Renamed"
    other.save()
    assert Store.objects.get(pk=other.pk).color == other.color  # never re-assigned


def test_dashboard_daily_sales_by_store(shop):
    import uuid as _uuid

    from django.contrib.auth import get_user_model
    from django.test import Client

    c = shop["client"]
    sale = _open(c)
    _add(c, sale["id"], shop["whey"], 1)
    _complete(c, sale["id"], amount_tendered="120000")
    staff = get_user_model().objects.create(username=f"nz_{_uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    admin = Client()
    admin.force_login(staff)
    for key in ("today", "7d", "30d", "this_month", "prev_month"):
        body = admin.get(f"/django-admin/pos/salemodel/by-store.json?range={key}").json()
        assert body["range"] == key and len(body["labels"]) == len(body["totals"])
    body = admin.get("/django-admin/pos/salemodel/by-store.json?range=today").json()
    mine = next(s for s in body["stores"] if s["id"] == str(shop["store"].id))
    assert body["granularity"] == "hour" and mine["total"] == 120000.0 and mine["color"] == shop["store"].color
    assert body["summary"]["total"] >= 120000.0 and body["summary"]["top"]["name"] == shop["store"].name
    custom = admin.get("/django-admin/pos/salemodel/by-store.json?range=custom&from=2026-01-01&to=2026-01-10").json()
    assert custom["from"] == "2026-01-01" and len(custom["labels"]) == 10
    assert Client().get("/django-admin/pos/salemodel/by-store.json").status_code in (302, 403)  # staff only
