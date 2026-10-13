"""
**Only `Quantity` is tested here** -- `Money` is the Shared Kernel's
own primitive, already tested wherever it was originally certified;
this build does not retest the entire Shared Kernel inside POS, per
this phase's own explicit instruction. The only POS-relevant `Money`
behavior (its non-negative construction invariant) is exercised
indirectly through `SaleLineItem`/`Sale.add_line_item()` tests, not
re-verified here in isolation.
"""
from __future__ import annotations

import pytest

from apps.pos.domain.exceptions import InvalidQuantity
from apps.pos.domain.value_objects import Quantity

pytestmark = pytest.mark.unit


class TestQuantity:
    def test_valid_positive_quantity(self):
        assert Quantity(5).value == 5

    def test_exactly_one_is_the_minimum_valid_value(self):
        Quantity(1)

    def test_rejects_zero_with_specific_exception(self):
        with pytest.raises(InvalidQuantity):
            Quantity(0)

    def test_rejects_negative_with_specific_exception(self):
        with pytest.raises(InvalidQuantity):
            Quantity(-1)

    def test_equality(self):
        assert Quantity(3) == Quantity(3)

    def test_immutability(self):
        quantity = Quantity(3)
        with pytest.raises(Exception):
            quantity.value = 10  # type: ignore[misc]
