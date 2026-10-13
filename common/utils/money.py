"""
Money value object.

This is one of exactly two items the Domain Architecture Specification
approves as Shared Kernel (§5 there): a single canonical Money
implementation used by Pricing, Wallet, Ordering, and Analytics, so
rounding/currency-handling never diverges across money-touching
contexts. A copy of this same class is re-exported from
`shared/value_objects/money.py` as the code-level home for the approved
Shared Kernel per Django Implementation Blueprint §1 -- defined once
here to avoid a duplicate implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

DEFAULT_CURRENCY = "UZS"
_QUANTIZE = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class Money:
    """Immutable money value object. Amount is always non-negative by construction."""

    amount: Decimal
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("Money amount must not be negative.")
        object.__setattr__(self, "amount", self.amount.quantize(_QUANTIZE, rounding=ROUND_HALF_UP))

    def _check_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError(f"Currency mismatch: {self.currency} vs {other.currency}")

    def __add__(self, other: "Money") -> "Money":
        self._check_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check_currency(other)
        result = self.amount - other.amount
        if result < 0:
            raise ValueError("Resulting Money amount would be negative.")
        return Money(result, self.currency)

    def __mul__(self, factor: Decimal | int) -> "Money":
        return Money(self.amount * Decimal(factor), self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._check_currency(other)
        return self.amount < other.amount

    def __le__(self, other: "Money") -> bool:
        self._check_currency(other)
        return self.amount <= other.amount

    @classmethod
    def zero(cls, currency: str = DEFAULT_CURRENCY) -> "Money":
        return cls(Decimal("0"), currency)

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"{self.amount} {self.currency}"
