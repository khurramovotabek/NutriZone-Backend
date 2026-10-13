"""
Cart domain (business) validators -- thin, intention-revealing
wrappers over the value objects' own constructor validation, matching
the pattern established by every prior module's domain/validators.py.
"""
from __future__ import annotations

from apps.cart.domain.value_objects import CartCode, CartNote, CurrencyCode, GiftMessage, Quantity, RegionCode


def CartCodeValidator(code: str) -> CartCode:  # noqa: N802
    return CartCode(code)


def QuantityValidator(value: int) -> Quantity:  # noqa: N802
    return Quantity(value)


def CartNoteValidator(text: str) -> CartNote:  # noqa: N802
    return CartNote(text)


def GiftMessageValidator(text: str) -> GiftMessage:  # noqa: N802
    return GiftMessage(text)


def CurrencyValidator(code: str) -> CurrencyCode:  # noqa: N802
    return CurrencyCode(code)


def RegionValidator(code: str) -> RegionCode:  # noqa: N802
    return RegionCode(code)


def MaxQuantityValidator(quantity: int, max_quantity: int = 999) -> None:  # noqa: N802
    from apps.cart.domain.exceptions import InvalidQuantity

    if quantity > max_quantity:
        raise InvalidQuantity(f"Quantity {quantity} exceeds the maximum allowed per line item ({max_quantity}).")


def ItemCountValidator(current_count: int, max_items: int = 200) -> None:  # noqa: N802
    """Guards against an unbounded number of distinct line items in a single cart -- a platform-level sanity limit, not a customer-facing business rule."""
    from common.exceptions import ValidationFailed

    if current_count >= max_items:
        raise ValidationFailed(f"A cart cannot hold more than {max_items} distinct line items.")
