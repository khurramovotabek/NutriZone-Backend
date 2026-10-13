"""
Test factories for Cart domain objects -- keeps every test file's
Arrange step short and consistent, per this phase's "no duplicated
setup" requirement. Every factory accepts overrides via **kwargs so
individual tests can vary just the field under test.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from apps.cart.domain.aggregates import Cart
from apps.cart.domain.entities import CartItem, PriceReference
from apps.cart.domain.enums import CartSource, CartType
from apps.cart.domain.value_objects import CartCode, CartToken, CurrencyCode, Money, Quantity

_COUNTER = {"value": 0}


def _next_code() -> str:
    _COUNTER["value"] += 1
    return f"TESTCART{_COUNTER['value']:04d}"


def make_cart(**overrides) -> Cart:
    defaults = dict(id=uuid.uuid4(), code=CartCode(_next_code()), token=CartToken(uuid.uuid4()), currency=CurrencyCode("UZS"), cart_type=CartType.GUEST, source=CartSource.WEB)
    defaults.update(overrides)
    return Cart(**defaults)


def make_cart_item(**overrides) -> CartItem:
    defaults = dict(id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=Quantity(1))
    defaults.update(overrides)
    return CartItem(**defaults)


def make_price_reference(unit_amount: str = "10.00", currency: str = "UZS", **overrides) -> PriceReference:
    defaults = dict(price_snapshot_id=uuid.uuid4(), unit_amount=Money(amount=Decimal(unit_amount), currency=currency), applied_at=datetime.utcnow())
    defaults.update(overrides)
    return PriceReference(**defaults)


def make_active_cart(item_count: int = 1, quantity: int = 2, **overrides) -> Cart:
    """A cart with the requirements for activation already met: at least one item, each with a price reference -- ready for checkout-readiness/validation tests without each test re-deriving this setup."""
    cart = make_cart(**overrides)
    now = datetime.utcnow()
    for _ in range(item_count):
        cart.add_item(uuid.uuid4(), quantity, now)
    for item in cart.items.values():
        cart.attach_price_snapshot(item.id, uuid.uuid4(), Money(amount=Decimal("50.00"), currency=cart.currency.value), now)
    return cart


def utcnow_plus(**timedelta_kwargs) -> datetime:
    return datetime.utcnow() + timedelta(**timedelta_kwargs)
