"""
POS domain exceptions.

**Written second, immediately after enums.py**, applying the lesson
learned repeatedly in this build (Reviews, Chat, Notifications,
Analytics Phase 1): `value_objects.py` will import its specific
exceptions directly from the start, so this file must exist first.

**`EmptySale` mirrors `apps.ordering.domain.exceptions.EmptyOrder`
exactly (same base class, same shape)** -- real, cited precedent for
why "cannot complete a transaction with zero items" is a genuine
structural invariant, not an invented business policy.
"""
from __future__ import annotations

from common.exceptions import BusinessRuleViolation, ConflictError, ValidationFailed


class InvalidQuantity(ValidationFailed):
    code = "INVALID_QUANTITY"


class EmptySale(BusinessRuleViolation):
    """Mirrors Ordering's own certified `EmptyOrder` precedent exactly."""

    code = "EMPTY_SALE"


class InvalidSaleTransition(ConflictError):
    """The general fallback for any wrong-state Sale transition (e.g. adding a line item to a COMPLETED or VOIDED sale, voiding an already-completed sale, completing an already-voided sale)."""

    code = "INVALID_SALE_TRANSITION"


class SaleLineItemNotFound(ValidationFailed):
    code = "SALE_LINE_ITEM_NOT_FOUND"
