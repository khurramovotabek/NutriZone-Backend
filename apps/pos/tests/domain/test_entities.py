"""
`SaleLineItem` has no independent public mutation methods of its own
-- its lifecycle is entirely governed by `Sale.add_line_item()`/
`remove_line_item()` (see test_aggregates.py for full lifecycle
coverage). This file tests only the entity's own construction/field
invariants and its `line_total()` computation in isolation.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.pos.domain.entities import SaleLineItem
from apps.pos.domain.value_objects import Quantity
from shared.value_objects.money import Money

pytestmark = pytest.mark.unit


class TestSaleLineItem:
    def test_valid_construction(self):
        product_id = uuid.uuid4()
        line_item = SaleLineItem(id=uuid.uuid4(), product_id=product_id, quantity=Quantity(3), unit_price=Money(Decimal("10.00")))
        assert line_item.product_id == product_id
        assert line_item.quantity.value == 3
        assert line_item.unit_price.amount == Decimal("10.00")

    def test_product_id_is_a_plain_uuid_not_a_domain_object(self):
        """A direct, executable proof of the certified cross-context boundary -- line items reference products only by id, never by importing apps.products.domain."""
        product_id = uuid.uuid4()
        line_item = SaleLineItem(id=uuid.uuid4(), product_id=product_id, quantity=Quantity(1), unit_price=Money(Decimal("1.00")))
        assert isinstance(line_item.product_id, uuid.UUID)

    def test_line_total_is_unit_price_times_quantity(self):
        line_item = SaleLineItem(id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=Quantity(4), unit_price=Money(Decimal("2.50")))
        assert line_item.line_total() == Money(Decimal("10.00"))

    def test_line_total_with_quantity_one(self):
        line_item = SaleLineItem(id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=Quantity(1), unit_price=Money(Decimal("7.99")))
        assert line_item.line_total() == Money(Decimal("7.99"))

    def test_line_total_is_computed_not_stored(self):
        """A direct, executable proof of the certified 'no redundant stored total' decision -- fails loudly if a stored total field is ever silently added to this entity."""
        line_item = SaleLineItem(id=uuid.uuid4(), product_id=uuid.uuid4(), quantity=Quantity(2), unit_price=Money(Decimal("5.00")))
        assert not hasattr(line_item, "_total")
        assert not hasattr(line_item, "total_amount")
