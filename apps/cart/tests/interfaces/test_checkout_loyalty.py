"""Checkout ↔ loyalty: paying part of an order with coins, through the real checkout endpoint."""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.cart.tests.interfaces.test_checkout_order_creation import (
    _client_as,
    _make_active_price_list_entry,
    _make_address,
    _make_geo,
    _make_user,
    _priced_cart,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def _setup(monkeypatch, coins: int, unit=Decimal("100000.00"), qty=2, suffix=91):
    from apps.loyalty.infrastructure import services

    country, city = _make_geo(city_code=f"LOY{suffix}")
    user_id = uuid.uuid4()
    _make_user(user_id, 9_000_000 + suffix)
    address = _make_address(user_id, country, city)
    variant_id = _make_active_price_list_entry(unit)
    if coins:
        services.adjust(user_id, coins, "test")
    client = _client_as(monkeypatch, user_id)
    cart, _item, _snap = _priced_cart(client, variant_id, quantity=qty)
    return user_id, address, client, cart


def _checkout(client, cart, address, coins):
    return client.post(
        f"/api/v1/cart/{cart['code']}/checkout", {"shipping_address_id": str(address.id), "coins_to_redeem": coins},
        format="json", HTTP_X_CART_TOKEN=cart["token"], HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
    )


def test_preview_offers_coins_up_to_the_cap(monkeypatch):
    user_id, address, client, cart = _setup(monkeypatch, coins=100_000, suffix=91)
    loyalty = client.get(f"/api/v1/cart/{cart['code']}/checkout-preview", HTTP_X_CART_TOKEN=cart["token"]).json()["data"]["loyalty"]
    assert loyalty == {"enabled": True, "balance": 100_000, "max_redeemable": 60_000, "max_percent": 30, "min_coins": 1000}  # 30% of 200 000


def test_checkout_with_coins_discounts_the_order_and_debits_the_wallet(monkeypatch):
    from apps.loyalty.infrastructure.models import Wallet, WalletTransaction
    from apps.ordering.infrastructure import composition as ordering_composition
    from apps.ordering.infrastructure import models as ordering_orm
    from apps.payment.application.services.create_payment import compute_order_payable_amount

    user_id, address, client, cart = _setup(monkeypatch, coins=100_000, suffix=92)
    r = _checkout(client, cart, address, 60_000)
    assert r.status_code == 201, r.json()
    order_id = r.json()["data"]["id"]

    line = ordering_orm.OrderLineItemModel.objects.get(order_id=order_id)
    assert line.discount_amount == Decimal("60000.00")
    order = ordering_composition.build_order_repository().get_by_id(uuid.UUID(order_id))
    assert compute_order_payable_amount(order) == Decimal("140000.00")  # what the customer is charged
    assert Wallet.objects.get(user_id=user_id).balance == 40_000
    assert WalletTransaction.objects.get(order_id=order_id, kind="spend").amount == -60_000


def test_checkout_rejects_coins_above_the_cap_and_creates_nothing(monkeypatch):
    from apps.loyalty.infrastructure.models import Wallet
    from apps.ordering.infrastructure import models as ordering_orm

    user_id, address, client, cart = _setup(monkeypatch, coins=100_000, suffix=93)
    r = _checkout(client, cart, address, 70_000)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "REDEEM_ABOVE_LIMIT"
    assert not ordering_orm.OrderModel.objects.filter(customer_id=user_id).exists()
    assert Wallet.objects.get(user_id=user_id).balance == 100_000


def test_checkout_rejects_more_coins_than_balance(monkeypatch):
    user_id, address, client, cart = _setup(monkeypatch, coins=5_000, suffix=94)
    r = _checkout(client, cart, address, 20_000)
    assert r.status_code == 409 and r.json()["error"]["code"] == "INSUFFICIENT_COINS"


def test_checkout_without_coins_is_unchanged(monkeypatch):
    from apps.ordering.infrastructure import models as ordering_orm

    user_id, address, client, cart = _setup(monkeypatch, coins=0, suffix=95)
    r = _checkout(client, cart, address, 0)
    assert r.status_code == 201
    assert ordering_orm.OrderLineItemModel.objects.get(order_id=r.json()["data"]["id"]).discount_amount == Decimal("0.00")
