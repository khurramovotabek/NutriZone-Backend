"""Online acquiring: Payme / Click / Uzum protocols, checkout start, methods list, dashboard pages, secret storage."""
from __future__ import annotations

import base64
import json
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth.models import User as StaffUser
from django.test import Client

from apps.identity.infrastructure.models import User
from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel, OrderPaymentReferenceModel
from apps.payment.infrastructure import service
from apps.payment.infrastructure.crypto import decrypt_secrets, encrypt_secrets, mask
from apps.payment.infrastructure.models import PaymentCallbackLog, PaymentModel, PaymentProviderConfig
from apps.payment.infrastructure.providers import click, payme

pytestmark = pytest.mark.django_db

PAYME_KEY = "payme-test-key-123"
CLICK_SECRET = "click-secret"
UZUM_LOGIN, UZUM_PASSWORD = "nz", "uzum-pass"


def _configure(provider: str, public: dict, secrets: dict, enabled=True, test=True):
    row, _ = PaymentProviderConfig.objects.get_or_create(provider=provider)
    row.settings_public = public
    row.secrets_encrypted = encrypt_secrets(secrets)
    row.is_enabled, row.is_test_mode = enabled, test
    row.save()
    return row


@pytest.fixture
def providers():
    _configure("payme", {"merchant_id": "5f1a2b3c", "account_field": "order_id"}, {"test_key": PAYME_KEY, "key": "prod-key"})
    _configure("click", {"service_id": "111", "merchant_id": "222"}, {"secret_key": CLICK_SECRET})
    _configure("uzum", {"service_id": "333", "login": UZUM_LOGIN}, {"password": UZUM_PASSWORD})


def _customer():
    return User.objects.create(phone_number=f"+99893{uuid.uuid4().int % 10_000_000:07d}", full_name="Pay Tester")


def _order(customer, amount="150000", status="pending_payment") -> OrderModel:
    o = OrderModel.objects.create(
        order_number=f"ORD-{uuid.uuid4().hex[:6].upper()}", customer_id=customer.id, currency="UZS", status=status,
        shipping_recipient_name="A", shipping_line1="B", shipping_city="T", shipping_country_code="UZ",
        billing_recipient_name="A", billing_line1="B", billing_city="T", billing_country_code="UZ",
    )
    OrderLineItemModel.objects.create(order=o, product_variant_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal(amount))
    return o


def _payme(client, method, params, key=PAYME_KEY):
    auth = "Basic " + base64.b64encode(f"Paycom:{key}".encode()).decode()
    r = client.post("/api/v1/payments/payme", json.dumps({"id": 7, "method": method, "params": params}), content_type="application/json", HTTP_AUTHORIZATION=auth)
    assert r.status_code == 200
    return r.json()


# ---------------------------------------------------------------- secrets


def test_secrets_are_encrypted_and_masked():
    token = encrypt_secrets({"key": "super-secret-value"})
    assert "super-secret" not in token
    assert decrypt_secrets(token) == {"key": "super-secret-value"}
    assert mask("super-secret-value") == "••••••alue"
    assert decrypt_secrets("garbage") == {}


# ---------------------------------------------------------------- methods + checkout


def test_methods_list_marks_unconfigured_as_coming_soon(client):
    data = {m["key"]: m for m in client.get("/api/v1/payments/methods").json()["data"]}
    assert data["cash"]["available"] is True
    for key in ("payme", "click", "uzum", "uzcard", "humo"):
        assert data[key]["status"] == "coming_soon" and data[key]["available"] is False


def test_methods_list_shows_configured_and_card_routes(client, providers):
    _configure("uzcard", {"route": "click"}, {})
    data = {m["key"]: m for m in client.get("/api/v1/payments/methods").json()["data"]}
    assert data["payme"]["available"] and data["payme"]["test_mode"]
    assert data["uzcard"]["available"] and data["uzcard"]["via"] == "click"
    assert data["humo"]["status"] == "coming_soon"  # still disabled


def _auth(client, user):
    from apps.identity.infrastructure.security import SimpleJWTTokenIssuer

    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {SimpleJWTTokenIssuer().issue(user.id).access_token}"
    return client


def test_customer_starts_payme_payment_and_gets_checkout_url(client, providers):
    u = _customer()
    o = _order(u)
    body = _auth(client, u).post(f"/api/v1/payments/orders/{o.order_number}/pay", {"method": "payme", "lang": "ru"}, content_type="application/json").json()
    assert body["success"], body
    url = body["data"]["checkout_url"]
    assert url.startswith("https://checkout.test.paycom.uz/")
    decoded = base64.b64decode(url.split("paycom.uz/", 1)[1]).decode()  # not rsplit("/"): base64 itself may contain "/"
    assert f"ac.order_id={o.order_number}" in decoded and "a=15000000" in decoded and "m=5f1a2b3c" in decoded and "l=ru" in decoded
    # a second click reuses the same attempt
    again = client.post(f"/api/v1/payments/orders/{o.order_number}/pay", {"method": "payme"}, content_type="application/json").json()
    assert again["data"]["payment_id"] == body["data"]["payment_id"]


def test_cannot_pay_someone_elses_or_unconfigured(client, providers):
    owner, other = _customer(), _customer()
    o = _order(owner)
    r = _auth(client, other).post(f"/api/v1/payments/orders/{o.order_number}/pay", {"method": "payme"}, content_type="application/json")
    assert r.status_code == 404
    PaymentProviderConfig.objects.filter(provider="payme").update(is_enabled=False)
    r = _auth(client, owner).post(f"/api/v1/payments/orders/{o.order_number}/pay", {"method": "payme"}, content_type="application/json")
    assert r.json()["error"]["code"] == "METHOD_NOT_AVAILABLE"


# ---------------------------------------------------------------- Payme


def test_payme_rejects_wrong_key(client, providers):
    assert _payme(client, "CheckPerformTransaction", {}, key="wrong")["error"]["code"] == payme.ERR_AUTH


def test_payme_check_perform_validates_amount_and_order(client, providers):
    o = _order(_customer())
    assert _payme(client, "CheckPerformTransaction", {"amount": 15000000, "account": {"order_id": o.order_number}})["result"] == {"allow": True}
    assert _payme(client, "CheckPerformTransaction", {"amount": 100, "account": {"order_id": o.order_number}})["error"]["code"] == payme.ERR_AMOUNT
    assert _payme(client, "CheckPerformTransaction", {"amount": 100, "account": {"order_id": "ORD-NOPE00"}})["error"]["code"] == payme.ERR_ORDER


def test_payme_full_flow_confirms_order_and_is_idempotent(client, providers):
    o = _order(_customer())
    params = {"id": "pm-1", "time": 1, "amount": 15000000, "account": {"order_id": o.order_number}}
    created = _payme(client, "CreateTransaction", params)["result"]
    assert created["state"] == 1
    assert _payme(client, "CreateTransaction", params)["result"]["transaction"] == created["transaction"]  # retry
    assert _payme(client, "CreateTransaction", {**params, "id": "pm-2"})["error"]["code"] == payme.ERR_ORDER_BUSY

    performed = _payme(client, "PerformTransaction", {"id": "pm-1"})["result"]
    assert performed["state"] == 2
    assert _payme(client, "PerformTransaction", {"id": "pm-1"})["result"]["perform_time"] == performed["perform_time"]

    o.refresh_from_db()
    assert o.status == "confirmed"
    assert OrderPaymentReferenceModel.objects.get(order=o).status == "captured"
    p = PaymentModel.objects.get(provider_reference="payme:pm-1")
    assert p.status == "succeeded" and p.paid_at is not None
    assert _payme(client, "CheckTransaction", {"id": "pm-1"})["result"]["state"] == 2
    assert _payme(client, "CheckPerformTransaction", {"amount": 15000000, "account": {"order_id": o.order_number}})["error"]["code"] == payme.ERR_ORDER_PAID
    statement = _payme(client, "GetStatement", {"from": 0, "to": 10**15})["result"]["transactions"]
    assert statement[0]["id"] == "pm-1" and statement[0]["account"] == {"order_id": o.order_number}
    assert PaymentCallbackLog.objects.filter(provider="payme", payment=p).count() >= 3


def test_payme_cancel_after_perform_refunds_until_shipped(client, providers):
    o = _order(_customer())
    _payme(client, "CreateTransaction", {"id": "pm-r", "time": 1, "amount": 15000000, "account": {"order_id": o.order_number}})
    _payme(client, "PerformTransaction", {"id": "pm-r"})
    OrderModel.objects.filter(pk=o.pk).update(status="shipped")
    assert _payme(client, "CancelTransaction", {"id": "pm-r", "reason": 5})["error"]["code"] == payme.ERR_CANT_CANCEL
    OrderModel.objects.filter(pk=o.pk).update(status="confirmed")
    res = _payme(client, "CancelTransaction", {"id": "pm-r", "reason": 5})["result"]
    assert res["state"] == -2
    assert PaymentModel.objects.get(provider_reference="payme:pm-r").status == "refunded"
    assert _payme(client, "CancelTransaction", {"id": "pm-r", "reason": 5})["result"]["cancel_time"] == res["cancel_time"]


def test_payme_expired_transaction_is_cancelled_with_reason_4(client, providers):
    o = _order(_customer())
    _payme(client, "CreateTransaction", {"id": "pm-old", "time": 1, "amount": 15000000, "account": {"order_id": o.order_number}})
    PaymentModel.objects.filter(provider_reference="payme:pm-old").update(provider_created_at=service.now_ms() - payme.TIMEOUT_MS - 1000)
    assert _payme(client, "PerformTransaction", {"id": "pm-old"})["error"]["code"] == payme.ERR_CANT_PERFORM
    check = _payme(client, "CheckTransaction", {"id": "pm-old"})["result"]
    assert check["state"] == -1 and check["reason"] == 4  # the cancellation survived the error answer
    assert _payme(client, "PerformTransaction", {"id": "unknown"})["error"]["code"] == payme.ERR_NOT_FOUND


# ---------------------------------------------------------------- Click


def _click(client, path, data):
    with_prepare = path == "complete"
    from apps.payment.infrastructure.providers.registry import load

    data = {"service_id": "111", "click_paydoc_id": "9", "error": "0", "error_note": "", "sign_time": "2026-10-08 10:00:00", **data}
    data["sign_string"] = click.signature(load("click"), data, with_prepare)
    return client.post(f"/api/v1/payments/click/{path}", data).json()


def test_click_prepare_complete_flow(client, providers):
    o = _order(_customer(), amount="99000")
    prep = _click(client, "prepare", {"click_trans_id": "c-1", "merchant_trans_id": o.order_number, "amount": "99000.00", "action": "0"})
    assert prep["error"] == click.OK and prep["merchant_prepare_id"]
    done = _click(client, "complete", {"click_trans_id": "c-1", "merchant_trans_id": o.order_number, "merchant_prepare_id": str(prep["merchant_prepare_id"]), "amount": "99000.00", "action": "1"})
    assert done["error"] == click.OK
    o.refresh_from_db()
    assert o.status == "confirmed"
    again = _click(client, "complete", {"click_trans_id": "c-1", "merchant_trans_id": o.order_number, "merchant_prepare_id": str(prep["merchant_prepare_id"]), "amount": "99000.00", "action": "1"})
    assert again["error"] == click.ERR_ALREADY_PAID


def test_click_rejects_bad_signature_amount_and_handles_failed_payment(client, providers):
    o = _order(_customer(), amount="99000")
    bad = client.post("/api/v1/payments/click/prepare", {"click_trans_id": "x", "service_id": "111", "merchant_trans_id": o.order_number, "amount": "99000", "action": "0", "sign_time": "t", "sign_string": "nope"}).json()
    assert bad["error"] == click.ERR_SIGN
    assert _click(client, "prepare", {"click_trans_id": "c-2", "merchant_trans_id": o.order_number, "amount": "10.00", "action": "0"})["error"] == click.ERR_AMOUNT
    prep = _click(client, "prepare", {"click_trans_id": "c-3", "merchant_trans_id": o.order_number, "amount": "99000", "action": "0"})
    failed = _click(client, "complete", {"click_trans_id": "c-3", "merchant_trans_id": o.order_number, "merchant_prepare_id": str(prep["merchant_prepare_id"]), "amount": "99000", "action": "1", "error": "-5017"})
    assert failed["error"] == click.ERR_CANCELLED
    assert PaymentModel.objects.get(provider_reference="click:c-3").status == "cancelled"
    o.refresh_from_db()
    assert o.status == "pending_payment"


# ---------------------------------------------------------------- Uzum


def _uzum(client, action, data, password=UZUM_PASSWORD):
    auth = "Basic " + base64.b64encode(f"{UZUM_LOGIN}:{password}".encode()).decode()
    return client.post(f"/api/v1/payments/uzum/{action}", json.dumps({"serviceId": 333, "timestamp": 1, **data}), content_type="application/json", HTTP_AUTHORIZATION=auth)


def test_uzum_flow_and_errors(client, providers):
    o = _order(_customer(), amount="50000")
    assert _uzum(client, "check", {"params": {"order_id": o.order_number}}, password="bad").json()["errorCode"] == "10001"
    assert _uzum(client, "check", {"params": {"order_id": "ORD-NONE00"}}).json()["errorCode"] == "10007"
    assert _uzum(client, "check", {"params": {"order_id": o.order_number}}).json()["status"] == "OK"
    assert _uzum(client, "create", {"transId": "u-1", "params": {"order_id": o.order_number}, "amount": 7000000}).json()["errorCode"] == "10011"
    created = _uzum(client, "create", {"transId": "u-1", "params": {"order_id": o.order_number}, "amount": 5000000}).json()
    assert created["status"] == "CREATED"
    confirmed = _uzum(client, "confirm", {"transId": "u-1"}).json()
    assert confirmed["status"] == "CONFIRMED"
    o.refresh_from_db()
    assert o.status == "confirmed"
    assert _uzum(client, "status", {"transId": "u-1"}).json()["status"] == "CONFIRMED"
    assert _uzum(client, "reverse", {"transId": "u-1"}).json()["status"] == "REVERSED"
    assert PaymentModel.objects.get(provider_reference="uzum:u-1").status == "refunded"


# ---------------------------------------------------------------- dashboard


@pytest.fixture
def boss():
    c = Client()
    c.force_login(StaffUser.objects.create_superuser(username=f"pay_{uuid.uuid4().hex[:6]}", password="x-pass-12345"))
    return c


def test_dashboard_pages_render(boss, providers, client):
    o = _order(_customer())
    _payme(client, "CreateTransaction", {"id": "pm-d", "time": 1, "amount": 15000000, "account": {"order_id": o.order_number}})
    p = PaymentModel.objects.get(provider_reference="payme:pm-d")
    row = PaymentProviderConfig.objects.get(provider="payme")
    for url in ("/django-admin/payment/paymentproviderconfig/", f"/django-admin/payment/paymentproviderconfig/{row.pk}/change/",
                "/django-admin/payment/paymentmodel/", "/django-admin/payment/paymentmodel/?status=pending", f"/django-admin/payment/paymentmodel/{p.pk}/change/",
                "/django-admin/payment/paymentcallbacklog/", "/django-admin/payment/paymentcallbacklog/?errors=1"):
        r = boss.get(url)
        assert r.status_code == 200, url
    assert "Payme" in boss.get(f"/django-admin/ordering/ordermodel/{o.pk}/change/").content.decode()  # order card lists the attempt
    page = boss.get(f"/django-admin/payment/paymentproviderconfig/{row.pk}/change/").content.decode()
    assert PAYME_KEY not in page and "/api/v1/payments/payme" in page


def test_dashboard_saves_secrets_encrypted_and_keeps_blank_ones(boss):
    row = PaymentProviderConfig.objects.get(provider="click")
    url = f"/django-admin/payment/paymentproviderconfig/{row.pk}/change/"
    r = boss.post(url, {"is_enabled": "on", "is_test_mode": "on", "service_id": "123", "merchant_id": "456", "secret_key": "s3cr3t", "min_amount": "1000"})
    assert r.status_code == 302
    row.refresh_from_db()
    assert "s3cr3t" not in row.secrets_encrypted and decrypt_secrets(row.secrets_encrypted)["secret_key"] == "s3cr3t"
    boss.post(url, {"is_enabled": "on", "service_id": "123", "merchant_id": "456", "secret_key": "", "min_amount": "1000"})
    row.refresh_from_db()
    assert decrypt_secrets(row.secrets_encrypted)["secret_key"] == "s3cr3t"
    assert boss.post(url, {"service_id": "abc", "merchant_id": "456", "min_amount": "1000"}).status_code == 200  # digits only → re-rendered with an error


def test_selftest_proves_credentials(boss, providers):
    for key in ("payme", "click", "uzum"):
        body = boss.post(f"/django-admin/payment/paymentproviderconfig/{key}/selftest/").json()
        assert body["ok"], (key, body)
    PaymentProviderConfig.objects.filter(provider="payme").update(secrets_encrypted="")
    assert boss.post("/django-admin/payment/paymentproviderconfig/payme/selftest/").json()["ok"] is False


def test_uzum_spec_codes_for_repeats_cancels_and_timeouts(client, providers):
    """Uzum Merchant API spec: repeated create/confirm/reverse, confirm after cancel, 30-minute confirm timeout, missing params."""
    o = _order(_customer(), amount="50000")
    assert _uzum(client, "confirm", {}).json()["errorCode"] == "10005"
    assert _uzum(client, "confirm", {"transId": "nope"}).json()["errorCode"] == "10014"
    body = {"transId": "u-9", "params": {"order_id": o.order_number}, "amount": 5000000}
    assert _uzum(client, "create", body).json()["status"] == "CREATED"
    r = _uzum(client, "create", body)
    assert r.status_code == 400 and r.json()["errorCode"] == "10010"
    assert _uzum(client, "reverse", {"transId": "u-9"}).json()["status"] == "REVERSED"
    assert _uzum(client, "reverse", {"transId": "u-9"}).json()["errorCode"] == "10018"
    assert _uzum(client, "confirm", {"transId": "u-9"}).json()["errorCode"] == "10015"
    # a new transaction confirmed twice
    assert _uzum(client, "create", {**body, "transId": "u-10"}).json()["status"] == "CREATED"
    assert _uzum(client, "confirm", {"transId": "u-10"}).json()["status"] == "CONFIRMED"
    assert _uzum(client, "confirm", {"transId": "u-10"}).json()["errorCode"] == "10016"
    assert _uzum(client, "status", {"transId": "u-10"}).json()["status"] == "CONFIRMED"


def test_uzum_unconfirmed_transaction_fails_after_30_minutes(client, providers):
    o = _order(_customer(), amount="50000")
    assert _uzum(client, "create", {"transId": "u-30", "params": {"order_id": o.order_number}, "amount": 5000000}).json()["status"] == "CREATED"
    PaymentModel.objects.filter(provider_reference="uzum:u-30").update(provider_created_at=1)
    assert _uzum(client, "confirm", {"transId": "u-30"}).json()["errorCode"] == "10015"
    assert PaymentModel.objects.get(provider_reference="uzum:u-30").status == "cancelled"
    # the order is still payable by a fresh transaction
    assert _uzum(client, "create", {"transId": "u-31", "params": {"order_id": o.order_number}, "amount": 5000000}).json()["status"] == "CREATED"


def test_uzum_amount_limits_and_param_key(client, providers):
    from apps.payment.infrastructure.models import PaymentProviderConfig

    row = PaymentProviderConfig.objects.get(provider="uzum")
    row.min_amount, row.max_amount = 60000, 70000
    row.settings_public = {**row.settings_public, "param_key": "account"}
    row.save()
    o = _order(_customer(), amount="50000")
    assert _uzum(client, "create", {"transId": "u-l", "params": {"account": o.order_number}, "amount": 5000000}).json()["errorCode"] == "10012"
    ok = _uzum(client, "check", {"params": {"account": o.order_number}}).json()
    assert ok["status"] == "OK" and ok["data"]["account"]["value"] == o.order_number


# ---------------------------------------------------------------- analytics / setup / health


def test_payment_analytics_numbers(client, providers):
    from apps.payment.infrastructure import insights

    o1, o2 = _order(_customer(), amount="50000"), _order(_customer(), amount="20000")
    _uzum(client, "create", {"transId": "a-1", "params": {"order_id": o1.order_number}, "amount": 5000000})
    _uzum(client, "confirm", {"transId": "a-1"})
    _uzum(client, "create", {"transId": "a-2", "params": {"order_id": o2.order_number}, "amount": 2000000})
    _uzum(client, "reverse", {"transId": "a-2"})
    an = insights.analytics(30)
    uz = next(p for p in an["providers"] if p["key"] == "uzum")
    assert uz["paid"] == 1 and uz["started"] == 2 and uz["success"] == 50.0
    assert an["totals"]["paid"] == 1 and an["totals"]["volume"] == 50000
    assert sum(an["chart"]["series"][0]["data"] if an["chart"]["series"][0]["key"] == "uzum" else next(s for s in an["chart"]["series"] if s["key"] == "uzum")["data"]) == 50000
    assert [f["n"] for f in an["funnel"]][:3] == [2, 2, 1]
    assert sum(h["n"] for h in an["hours"]) == 1


def test_callback_stats_and_error_explanations(client, providers):
    from apps.payment.infrastructure import insights

    o = _order(_customer(), amount="50000")
    _uzum(client, "check", {"params": {"order_id": "ORD-NONE00"}})
    _uzum(client, "check", {"params": {"order_id": o.order_number}})
    st = insights.callback_stats(7)
    assert st["total"] >= 2 and st["errors"] >= 1
    top = next(e for e in st["top"] if e["provider"] == "uzum")
    assert top["code"] == 10007 and top["expected"] and top["title"] == "Buyurtma topilmadi"
    assert insights.explain("payme", -31001)[0] == "Summa noto'g'ri"
    assert insights.explain("click", None) == ("OK", "")


def test_credential_checks_and_readiness(providers):
    from apps.payment.infrastructure import insights
    from apps.payment.infrastructure.models import PaymentProviderConfig
    from apps.payment.infrastructure.providers import registry

    row = PaymentProviderConfig.objects.get(provider="payme")
    row.settings_public = {**row.settings_public, "merchant_id": "not-hex"}
    row.save()
    state = registry.load("payme")
    assert any(c["field"] == "merchant_id" and c["level"] == "bad" for c in insights.credential_checks(state))
    r = insights.readiness(state, row, "https://nutrizone.uz")
    keys = {i["key"]: i["ok"] for i in r["items"]}
    assert keys["https"] and not keys["format"] and not keys["selftest"]
    assert 0 < r["score"] < 100 and r["next"]
    insights.save_selftest(row, True, -31050)
    row.refresh_from_db()
    assert insights.readiness(registry.load("payme"), row, "https://x.uz")["tested_fresh"]


def test_selftest_records_result_and_pages_render(boss, providers, client):
    from apps.payment.infrastructure.models import PaymentProviderConfig

    r = boss.post("/django-admin/payment/paymentproviderconfig/uzum/selftest/").json()
    assert r["ok"] and "Buyurtma topilmadi" in r["explain"]
    assert PaymentProviderConfig.objects.get(provider="uzum").settings_public["_selftest"]["ok"] is True
    row = PaymentProviderConfig.objects.get(provider="uzum")
    page = boss.get(f"/django-admin/payment/paymentproviderconfig/{row.pk}/change/")
    assert page.status_code == 200 and b"pay-checklist" in page.content
    o = _order(_customer(), amount="50000")
    _uzum(client, "create", {"transId": "p-1", "params": {"order_id": o.order_number}, "amount": 5000000})
    _uzum(client, "confirm", {"transId": "p-1"})
    for url in ("/django-admin/payment/paymentproviderconfig/", "/django-admin/payment/paymentmodel/?days=7", "/django-admin/payment/paymentmodel/?days=90&provider__exact=uzum",
                "/django-admin/payment/paymentcallbacklog/", "/django-admin/payment/paymentreconciliationissue/"):
        resp = boss.get(url)
        assert resp.status_code == 200, url
    assert b"pay-daily" in boss.get("/django-admin/payment/paymentmodel/").content
    for url in ("/django-admin/payment/paymentmodel/analytics.xlsx?days=30", "/django-admin/payment/paymentcallbacklog/export.xlsx"):
        resp = boss.get(url)
        assert resp.status_code == 200 and resp.content[:2] == b"PK", url
    from io import BytesIO

    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(boss.get("/django-admin/payment/paymentmodel/analytics.xlsx").content))
    assert wb.sheetnames == ["Xulosa", "Provayderlar", "Kunlik", "Voronka", "Callback"]


def test_reconcile_flags_open_transaction_on_cancelled_order(client, providers):
    from apps.payment.infrastructure import reconcile
    from apps.payment.infrastructure.models import PaymentReconciliationIssue

    o = _order(_customer(), amount="50000")
    _uzum(client, "create", {"transId": "r-1", "params": {"order_id": o.order_number}, "amount": 5000000})
    type(o).objects.filter(pk=o.pk).update(status="cancelled")
    reconcile.run(external=False)
    assert PaymentReconciliationIssue.objects.filter(kind="open_txn_order_closed", status="open").exists()
