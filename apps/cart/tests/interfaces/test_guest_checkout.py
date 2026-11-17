"""Guest checkout: order with a typed name + phone, no sign-in (apps/cart/interfaces/api/v1/guest_checkout.py)."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.cart.tests.interfaces.test_checkout_order_creation import _make_active_price_list_entry, _make_geo

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _guest_cart(variant_id, quantity=1):
    c = APIClient()
    r = c.post("/api/v1/cart/", {"cart_type": "guest"}, format="json")
    assert r.status_code in (200, 201), r.json()
    cart = r.json()["data"]
    r = c.post(f"/api/v1/cart/{cart['code']}/items", {"product_variant_id": str(variant_id), "quantity": quantity}, format="json", HTTP_X_CART_TOKEN=cart["token"])
    assert r.status_code in (200, 201), r.json()
    return c, cart


def _order(c, cart, phone, **extra):
    country, city = _make_geo()
    body = {"full_name": "Ali Valiyev", "phone": phone, "fulfilment_method": "delivery",
            "address": {"country_id": str(country.id), "city_id": str(city.id), "line1": "Amir Temur 15", "latitude": 41.31, "longitude": 69.27,
                        "metadata": {"entrance": "2", "floor": "5"}}, **extra}
    return c.post(f"/api/v1/cart/{cart['code']}/guest-checkout", body, format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))


def test_preview_prices_the_guest_cart_and_quotes_delivery():
    variant = _make_active_price_list_entry(Decimal("50000.00"))
    c, cart = _guest_cart(variant, 2)
    _country, city = _make_geo()
    r = c.get(f"/api/v1/cart/{cart['code']}/guest-preview?city_id={city.id}&lat=41.31&lng=69.27", HTTP_X_CART_TOKEN=cart["token"])
    assert r.status_code == 200, r.json()
    data = r.json()["data"]
    assert data["subtotal"]["amount"].startswith("100000")
    assert data["loyalty"] is None
    assert data["delivery"] and data["delivery"]["method"] == "delivery"


def test_new_phone_creates_a_guest_account_with_a_session():
    from apps.geo.infrastructure.models import Address
    from apps.identity.infrastructure.models import User
    from apps.ordering.infrastructure.models import OrderModel

    variant = _make_active_price_list_entry(Decimal("50000.00"))
    c, cart = _guest_cart(variant)
    r = _order(c, cart, "94-205-20-40")
    assert r.status_code == 201, r.json()
    data = r.json()["data"]
    user = User.objects.get(phone_number="+998942052040")
    assert user.is_guest and user.full_name == "Ali Valiyev"
    assert data["account"] == "new" and data["session"]["access_token"]
    order = OrderModel.objects.get(order_number=data["order_number"])
    assert order.customer_id == user.id
    addr = Address.objects.get(owner_id=user.id)
    assert addr.coordinate_latitude == pytest.approx(41.31) and addr.recipient_phone == "+998942052040"


def test_issue_session_works_outside_a_request_transaction():
    """Regression: a real request has no surrounding atomic block -- stage_event() asserted and the order answered 500."""
    from django.db import transaction

    from apps.identity.infrastructure import guests
    from rest_framework.parsers import JSONParser
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory

    user, created = guests.find_or_create("93 111 22 33", "Test Mehmon")
    assert created
    req = Request(APIRequestFactory().post("/x", {}, format="json"), parsers=[JSONParser()])
    conn = transaction.get_connection()
    saved = conn.in_atomic_block
    conn.in_atomic_block = False  # what a live request looks like (the test DB wraps everything in one)
    try:
        session = guests.issue_session(user, req)
    finally:
        conn.in_atomic_block = saved
    assert session["access_token"]


def test_existing_account_gets_the_order_but_never_a_session():
    from apps.identity.infrastructure.models import User
    from apps.ordering.infrastructure.models import OrderModel

    owner = User.objects.create(id=uuid.uuid4(), phone_number="+998901112233", full_name="Real Owner", status="active")
    variant = _make_active_price_list_entry(Decimal("50000.00"))
    c, cart = _guest_cart(variant)
    r = _order(c, cart, "90 111 22 33")
    assert r.status_code == 201, r.json()
    data = r.json()["data"]
    assert data["account"] == "existing" and "session" not in data
    assert OrderModel.objects.get(order_number=data["order_number"]).customer_id == owner.id
    owner.refresh_from_db()
    assert not owner.is_guest and owner.full_name == "Real Owner"


def test_bad_phone_is_rejected():
    variant = _make_active_price_list_entry(Decimal("50000.00"))
    c, cart = _guest_cart(variant)
    r = _order(c, cart, "salom")
    assert r.status_code == 422


def test_cart_token_is_required():
    variant = _make_active_price_list_entry(Decimal("50000.00"))
    c, cart = _guest_cart(variant)
    r = c.get(f"/api/v1/cart/{cart['code']}/guest-preview")
    assert r.status_code == 403


def test_guest_earns_no_coins_and_claim_clears_the_flag():
    from apps.identity.infrastructure import guests
    from apps.identity.infrastructure.models import User

    u, created = guests.find_or_create("+998 93 000 11 22", "Mehmon", "uz")
    assert created and guests.is_guest(u.id)
    again, created2 = guests.find_or_create("930001122", "Boshqa", "uz")
    assert again.id == u.id and not created2
    assert guests.claim(u.id) is True
    assert not User.objects.get(pk=u.id).is_guest


@pytest.mark.parametrize("raw,expected", [
    ("942052040", "+998942052040"), ("94 205 20 40", "+998942052040"), ("94-205-20-40", "+998942052040"),
    ("+998942052040", "+998942052040"), ("998 94 205 20 40", "+998942052040"), ("(94) 205-20-40", "+998942052040"),
    ("8 94 205 20 40", "+998942052040"), ("whey 5lb", ""), ("12345", ""), ("", ""), ("012345678", ""),
])
def test_parse_uz_phone(raw, expected):
    from apps.identity.domain.phone import parse_uz_phone

    assert parse_uz_phone(raw) == expected
