"""
Test factories for Ordering domain objects -- keeps every test file's
Arrange step short and consistent, per this phase's "no duplicated
setup" requirement. Every factory accepts overrides via **kwargs so
individual tests can vary just the field under test.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from apps.ordering.domain.aggregates import Order, OrderCancellation, OrderReturn
from apps.ordering.domain.entities import OrderLineItem
from apps.ordering.domain.enums import OrderChannel, OrderStatus
from apps.ordering.domain.value_objects import AddressSnapshot, Money, OrderNumber, ReturnNumber

_COUNTER = {"value": 0}


def _next_order_number() -> str:
    _COUNTER["value"] += 1
    return f"ORD-{_COUNTER['value']:010d}"


def _next_return_number() -> str:
    _COUNTER["value"] += 1
    return f"RET-{_COUNTER['value']:010d}"


def make_address(**overrides) -> AddressSnapshot:
    defaults = dict(recipient_name="Jane Doe", line1="123 Main St", city="Tashkent", country_code="UZ")
    defaults.update(overrides)
    return AddressSnapshot(**defaults)


def make_line_item(**overrides) -> OrderLineItem:
    defaults = dict(
        id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=2,
        unit_price=Money(amount=Decimal("50.00"), currency="UZS"),
        discount_amount=Money(amount=Decimal("0.00"), currency="UZS"),
        tax_amount=Money(amount=Decimal("0.00"), currency="UZS"),
    )
    defaults.update(overrides)
    return OrderLineItem(**defaults)


def make_order(**overrides) -> Order:
    defaults = dict(
        id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=uuid.uuid4(), cart_id=uuid.uuid4(),
        shipping_address=make_address(), billing_address=make_address(), currency="UZS", channel=OrderChannel.WEB,
        lines={}, placed_at=datetime.utcnow(),
    )
    defaults.update(overrides)
    return Order(**defaults)


def make_order_with_line(**overrides) -> Order:
    line = make_line_item()
    overrides.setdefault("status", OrderStatus.PENDING_PAYMENT)
    order = make_order(lines={line.id: line}, **overrides)
    return order


def make_confirmed_order(**overrides) -> Order:
    """
    An order past PENDING_PAYMENT -- ready for the rest of the
    status-transition chain without each test re-deriving this setup.
    Explicitly sets `status=PENDING_PAYMENT` before calling `.confirm()`
    -- `make_order()`'s own raw-dataclass-constructor default is
    `OrderStatus.DRAFT` (matching `Order`'s own domain default),
    so without this override `.confirm()` genuinely raises
    `InvalidOrderLifecycleTransition`, confirmed directly: this was a
    real, pre-existing factory bug (never caught before, since this
    test suite had never actually executed against Django/pytest
    until this project's compatibility-hardening phase), not
    something introduced here.
    """
    order = make_order_with_line(status=OrderStatus.PENDING_PAYMENT, **overrides)
    order.confirm(datetime.utcnow())
    return order


def make_delivered_order(**overrides) -> Order:
    order = make_confirmed_order(**overrides)
    order.start_processing(datetime.utcnow())
    order.ship(datetime.utcnow())
    order.deliver(datetime.utcnow())
    return order


def make_return(**overrides) -> OrderReturn:
    defaults = dict(id=uuid.uuid4(), return_number=ReturnNumber(_next_return_number()), order_id=uuid.uuid4(), requested_at=datetime.utcnow())
    defaults.update(overrides)
    return OrderReturn(**defaults)


def make_cancellation(**overrides) -> OrderCancellation:
    defaults = dict(id=uuid.uuid4(), order_id=uuid.uuid4(), requested_at=datetime.utcnow())
    defaults.update(overrides)
    return OrderCancellation(**defaults)
