"""
POS domain value objects.

**`Money` is NOT reinvented here** -- it is one of exactly two items
the Domain Architecture Specification approves as Shared Kernel (§5),
already used by Pricing, Wallet, and Ordering. POS reuses
`shared.value_objects.money.Money` directly for `SaleLineItem.
unit_price` and `Sale.total()`, per this task's own explicit rule
against duplicating capability that already exists.

**Only `Quantity` is genuinely POS-specific** -- a positive integer
count of countable retail units. No evidence anywhere in this
repository supports fractional or weighted line items (no "kg"/"per-
unit-weight" concept exists on any Product aggregate inspected during
Step 1), so this VO is deliberately integer-only, not a generic
Decimal.
"""
from __future__ import annotations

from dataclasses import dataclass

from apps.pos.domain.exceptions import InvalidQuantity


@dataclass(frozen=True, slots=True)
class Quantity:
    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise InvalidQuantity(f"Quantity must be a positive integer (got {self.value}).", details={"fields": [{"field": "quantity", "code": "NOT_POSITIVE"}]})
