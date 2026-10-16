import json
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.receipts.infrastructure import builders, fiscal
from apps.receipts.infrastructure.models import Receipt, ReceiptSettings

pytestmark = pytest.mark.django_db


def _variant(name="Zorvex Whey", mxik="02106001001000000"):
    from apps.products.infrastructure import models as p

    product = p.Product.objects.create(id=uuid.uuid4(), status="published", mxik_code=mxik, package_code="1515130")
    p.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name=name, slug=f"s-{uuid.uuid4().hex[:8]}")
    return p.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"S-{uuid.uuid4().hex[:6]}", status="active", is_default=True)


def test_manual_receipt_numbers_vat_and_tax_codes():
    s = ReceiptSettings.get()
    s.vat_payer, s.vat_rate, s.tin, s.legal_name = True, Decimal("12"), "123456789", "NUTRIZONE MChJ"
    s.save()
    v = _variant()
    r = builders.manual(lines=[{"variant_id": str(v.id), "name": "Zorvex Whey", "quantity": 2, "unit_price": "560000"}], customer_name="Aziz", staff="Kassir")
    assert r.number.startswith("NZM-") and r.total == Decimal("1120000") and r.vat_amount == Decimal("120000.00")
    assert r.data["items"][0]["mxik"] == "02106001001000000" and r.data["requisites"]["tin"] == "123456789"
    second = builders.manual(lines=[{"name": "X", "quantity": 1, "unit_price": "1000"}])
    assert int(second.number.split("-")[1]) == int(r.number.split("-")[1]) + 1


def test_bad_manual_lines_rejected():
    with pytest.raises(ValueError):
        builders.manual(lines=[])
    with pytest.raises(ValueError):
        builders.manual(lines=[{"name": "X", "quantity": 0, "unit_price": "100"}])


def test_fiscalize_needs_provider_settings_and_mxik_then_stores_sign():
    r = builders.manual(lines=[{"variant_id": str(_variant(mxik="").id), "name": "No code", "quantity": 1, "unit_price": "1000"}])
    with pytest.raises(fiscal.FiscalError, match="ulanmagan"):
        fiscal.fiscalize(r)
    s = ReceiptSettings.get()
    s.fiscal_provider, s.fiscal_endpoint, s.fiscal_terminal_id, s.tin = "http", "https://ofd.example/api/receipts", "EP000000001", "123456789"
    s.save()
    with pytest.raises(fiscal.FiscalError, match="MXIK"):
        fiscal.fiscalize(r)
    ok = builders.manual(lines=[{"variant_id": str(_variant().id), "name": "Whey", "quantity": 1, "unit_price": "1000"}])
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"data": {"fiscal_number": "000123", "fiscal_sign": "FS-998877", "qr_url": "https://ofd.soliq.uz/check?t=EP1&r=123"}}
    with patch("apps.receipts.infrastructure.fiscal.requests.post", return_value=resp) as post:
        ok = fiscal.fiscalize(ok)
    payload = post.call_args.kwargs["json"]
    assert payload["terminal_id"] == "EP000000001" and payload["items"][0]["price"] == 100000 and payload["items"][0]["mxik"]  # tiyin
    assert ok.status == "fiscalized" and ok.fiscal_sign == "FS-998877" and ok.fiscal_url.startswith("https://ofd.soliq.uz")


def test_public_receipt_page_serves_manual_receipts_masked(client):
    r = builders.manual(lines=[{"name": "Whey", "quantity": 1, "unit_price": "1000"}], customer_name="Aziz Karimov", customer_phone="+998901234567")
    data = client.get(f"/api/v1/receipts/{r.token}").json()["data"]
    assert data["number"] == r.number and data["customer"]["name"] == "Aziz"
    assert "**" in data["customer"]["phone"] and data["fiscal"] is None


def test_dashboard_pages(admin_client):
    r = builders.manual(lines=[{"name": "Whey", "quantity": 1, "unit_price": "1000"}])
    for url in ("/django-admin/receipts/receipt/", f"/django-admin/receipts/receipt/{r.pk}/change/", f"/django-admin/receipts/receipt/{r.pk}/print/?w=80",
                f"/django-admin/receipts/receipt/{r.pk}/print/?w=a4", "/django-admin/receipts/receipt/new/", "/django-admin/receipts/receiptsettings/"):
        assert admin_client.get(url, follow=True).status_code == 200, url
    v = _variant()
    resp = admin_client.post("/django-admin/receipts/receipt/new/", {"lines": json.dumps([{"variant_id": str(v.id), "name": "W", "quantity": 1, "unit_price": 5000}]), "payment_method": "card", "kind": "sale"})
    assert resp.status_code == 302 and Receipt.objects.filter(payment_method="card").exists()


def test_my_receipts_lists_only_the_customers_own(monkeypatch):
    from types import SimpleNamespace

    from rest_framework.test import APIClient

    from apps.identity.infrastructure.models import User

    user = User.objects.create(id=uuid.uuid4(), phone_number="+998901112233", status="active")
    mine = builders.manual(lines=[{"name": "Whey", "quantity": 1, "unit_price": "1000"}], customer_phone="+998901112233")
    builders.manual(lines=[{"name": "Other", "quantity": 1, "unit_price": "1000"}], customer_phone="+998909999999")
    assert APIClient().get("/api/v1/receipts/mine").status_code in (401, 403)
    fake = SimpleNamespace(id=user.id, is_authenticated=True, store_ids=set(), permissions=frozenset())
    monkeypatch.setattr("apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate", lambda self, request: (fake, None))
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake")
    data = client.get("/api/v1/receipts/mine").json()["data"]
    assert [r["number"] for r in data] == [mine.number] and data[0]["token"] == mine.token and data[0]["items"] == 1
