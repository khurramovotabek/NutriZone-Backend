"""
Test factories for POS domain objects -- keeps every test file's
Arrange step short and consistent. `make_sale` constructs exclusively
through the real public `Sale.open()` factory method, and
`make_sale_with_line` additionally uses the real public
`add_line_item()` method -- never direct field assignment or
private-member access.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from apps.pos.domain.aggregates import Sale
from apps.pos.domain.value_objects import Quantity
from shared.value_objects.money import Money


def make_sale(**overrides) -> Sale:
    sale_id = overrides.pop("sale_id", uuid.uuid4())
    branch_id = overrides.pop("branch_id", uuid.uuid4())
    cashier_id = overrides.pop("cashier_id", uuid.uuid4())
    customer_id = overrides.pop("customer_id", None)
    at = overrides.pop("at", datetime.utcnow())
    sale, _ = Sale.open(sale_id, branch_id, cashier_id, at, customer_id)
    for key, value in overrides.items():
        setattr(sale, key, value)
    return sale


def make_sale_with_line(quantity: int = 1, unit_price: str = "10.00", **overrides) -> Sale:
    """Convenience factory -- an opened sale with exactly one real line item added via `add_line_item()`."""
    sale = make_sale(**overrides)
    sale.add_line_item(uuid.uuid4(), Quantity(quantity), Money(Decimal(unit_price)))
    return sale


def make_money(amount: str = "10.00", currency: str = "UZS") -> Money:
    return Money(Decimal(amount), currency)
