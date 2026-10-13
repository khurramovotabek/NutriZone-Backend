"""
Cart domain exceptions.
"""
from __future__ import annotations

from common.exceptions import BusinessRuleViolation, ConflictError, ValidationFailed


class CartLocked(BusinessRuleViolation):
    code = "CART_LOCKED"


class CartAlreadyLocked(ConflictError):
    code = "CART_ALREADY_LOCKED"


class CartNotLocked(ConflictError):
    code = "CART_NOT_LOCKED"


class CartExpired(BusinessRuleViolation):
    code = "CART_EXPIRED"


class CartArchived(ConflictError):
    code = "CART_ARCHIVED"


class CartAlreadyConverted(ConflictError):
    code = "CART_ALREADY_CONVERTED"


class InvalidCartLifecycleTransition(ConflictError):
    code = "INVALID_CART_LIFECYCLE_TRANSITION"


class CartItemNotFound(ValidationFailed):
    code = "CART_ITEM_NOT_FOUND"


class InvalidQuantity(ValidationFailed):
    code = "INVALID_QUANTITY"


class EmptyCart(BusinessRuleViolation):
    code = "EMPTY_CART"


class CartNotEligibleForCheckout(BusinessRuleViolation):
    code = "CART_NOT_ELIGIBLE_FOR_CHECKOUT"


class CartOwnershipConflict(ConflictError):
    """Raised when attempting to assign a customer to a cart that already has a different customer_id -- an authenticated cart's ownership is not reassignable, only a guest cart's is (via assign_customer)."""

    code = "CART_OWNERSHIP_CONFLICT"


class CartMergeConflict(ConflictError):
    code = "CART_MERGE_CONFLICT"


class CartSnapshotNotFound(ValidationFailed):
    code = "CART_SNAPSHOT_NOT_FOUND"


class CurrencyMismatch(BusinessRuleViolation):
    """Raised when a SINGLE_CURRENCY cart receives an item priced in a different currency than the cart's own."""

    code = "CURRENCY_MISMATCH"


class CartValidationFailed(BusinessRuleViolation):
    """Raised by ValidateCart-adjacent flows when validation issues include at least one ERROR-severity issue -- WARNING-only results do not raise, they're returned for the caller to inspect."""

    code = "CART_VALIDATION_FAILED"


class CartEntityNotFound(ValidationFailed):
    code = "CART_ENTITY_NOT_FOUND"
