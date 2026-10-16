"""Fiscal receipts via Payme's virtual kassa (detail in CheckPerformTransaction, SetFiscalData) and the E-POS adapter."""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel
from apps.payment.infrastructure.models import PaymentModel
from apps.payment.infrastructure.providers import payme
from apps.payment.tests.test_online_acquiring import _customer, _payme, providers  # noqa: F401 (fixture)
from apps.receipts.infrastructure import builders, fiscal
from apps.receipts.infrastructure.models import Receipt, ReceiptSettings
from apps.receipts.tests.test_receipts import _variant

pytestmark = pytest.mark.django_db


def _order(lines, status="pending_payment", shipping=None) -> OrderModel:
    o = OrderModel.objects.create(
        order_number=f"ORD-{uuid.uuid4().hex[:6].upper()}", customer_id=_customer().id, currency="UZS", status=status,
        shipping_recipient_name="A", shipping_line1="B", shipping_city="T", shipping_country_code="UZ",
        billing_recipient_name="A", billing_line1="B", billing_city="T", billing_country_code="UZ",
        **({"shipping_estimated_amount": Decimal(shipping)} if shipping else {}),
    )
    for variant, qty, price, discount in lines:
        OrderLineItemModel.objects.create(order=o, product_variant_id=variant.id, quantity=qty, unit_price_amount=Decimal(price), discount_amount=Decimal(discount))
    return o


def _on(vat=False):
    s = ReceiptSettings.get()
    s.payme_fiscal, s.vat_payer, s.vat_rate, s.tin, s.legal_name = True, vat, Decimal("12"), "123456789", "YaTT Test"
    s.save()


def test_check_perform_sends_a_detail_that_adds_up_to_the_charged_amount(client, providers):
    _on(vat=True)
    whey, creatine = _variant("Whey"), _variant("Creatine")
    o = _order([(whey, 2, "505000", "10000"), (creatine, 1, "150000", "0")])
    amount = (2 * 505000 - 10000 + 150000) * 100
    result = _payme(client, "CheckPerformTransaction", {"amount": amount, "account": {"order_id": o.order_number}})["result"]
    d = result["detail"]
    assert result["allow"] is True and d["receipt_type"] == 0 and "shipping" not in d
    first = next(i for i in d["items"] if i["title"].startswith("Whey"))
    assert first == {"title": first["title"], "price": 50500000, "count": 2, "code": "02106001001000000", "package_code": "1515130", "vat_percent": 12.0, "discount": 1000000}
    assert sum(i["price"] * i["count"] - i.get("discount", 0) for i in d["items"]) == amount


def test_no_detail_when_off_or_a_product_has_no_tax_code(client, providers):
    o = _order([(_variant("Whey"), 1, "100000", "0")])
    params = {"amount": 10000000, "account": {"order_id": o.order_number}}
    assert _payme(client, "CheckPerformTransaction", params)["result"] == {"allow": True}  # switched off
    _on()
    o2 = _order([(_variant("No code", mxik=""), 1, "100000", "0")])
    assert _payme(client, "CheckPerformTransaction", {**params, "account": {"order_id": o2.order_number}})["result"] == {"allow": True}  # payment never blocked


def test_set_fiscal_data_lands_on_the_payment_and_the_receipt(client, providers):
    _on()
    o = _order([(_variant("Whey"), 1, "100000", "0")])
    params = {"id": "pm-fx", "time": 1, "amount": 10000000, "account": {"order_id": o.order_number}}
    _payme(client, "CreateTransaction", params)
    _payme(client, "PerformTransaction", {"id": "pm-fx"})
    fiscal_data = {"receipt_id": 121, "status_code": 0, "message": "", "terminal_id": "EP000000000025", "fiscal_sign": "123456789012",
                   "qr_code_url": "https://ofd.soliq.uz/epi?t=EP000000000025&r=121&c=20261016&s=123456789012", "date": "20261016120000"}
    assert _payme(client, "SetFiscalData", {"id": "pm-fx", "type": "PERFORM", "fiscal_data": fiscal_data})["result"] == {"success": True}
    p = PaymentModel.objects.get(provider_reference="payme:pm-fx")
    assert p.meta["fiscal"]["perform"]["fiscal_sign"] == "123456789012"
    OrderModel.objects.filter(pk=o.pk).update(status="delivered")
    o.refresh_from_db()
    r = builders.from_order(o)  # the receipt made at delivery carries Payme's tax QR
    assert r.status == "fiscalized" and r.fiscal_provider == "payme" and r.fiscal_url.startswith("https://ofd.soliq.uz") and r.fiscal_number == "121"
    assert _payme(client, "SetFiscalData", {"id": "nope", "type": "PERFORM", "fiscal_data": fiscal_data})["error"]["code"] == payme.ERR_RECEIPT_NOT_FOUND
    assert _payme(client, "SetFiscalData", {"id": "pm-fx", "type": "X", "fiscal_data": fiscal_data})["error"]["code"] == payme.ERR_PARAMS


def test_epos_adapter_sends_tax_codes_and_reads_the_fiscal_mark():
    s = ReceiptSettings.get()
    s.fiscal_provider, s.fiscal_endpoint, s.fiscal_terminal_id, s.fiscal_cashier_id, s.tin = "epos", "https://api.epos.uz/v1/receipts", "EP1", "CSH-007", "123456789"
    s.set_fiscal_secret("epos-token")
    s.save()
    r = builders.manual(lines=[{"variant_id": str(_variant().id), "name": "Whey", "quantity": 2, "unit_price": "12000"}], payment_method="payme")
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"data": {"id": "R-77", "fiscal_mark": "FM-1", "verification_url": "https://ofd.soliq.uz/check?r=77"}}
    with patch("apps.receipts.infrastructure.fiscal.requests.post", return_value=resp) as post:
        r = fiscal.fiscalize(r)
    body = post.call_args.kwargs["json"]
    assert body["cashier_id"] == "CSH-007" and body["items"][0] == {"name": "Whey", "price": 12000.0, "qty": 2, "ikpu": "02106001001000000",
                                                                    "package_code": "1515130", "vat_percent": 0, "barcode": ""}
    assert body["payment"] == {"method": "qr", "provider": "payme", "amount": 24000.0}
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer epos-token"}
    assert r.status == "fiscalized" and r.fiscal_sign == "FM-1" and r.fiscal_url.endswith("r=77")
    assert Receipt.objects.get(pk=r.pk).fiscal_number == "R-77"
