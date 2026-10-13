"""
Ordering domain exceptions.
"""
from __future__ import annotations

from common.exceptions import BusinessRuleViolation, ConflictError, ValidationFailed


class InvalidOrderLifecycleTransition(ConflictError):
    code = "INVALID_ORDER_LIFECYCLE_TRANSITION"


class OrderNotModifiable(BusinessRuleViolation):
    """Raised when attempting to mutate line items/addresses on an order that has progressed past DRAFT/PENDING_PAYMENT -- an order's contents are frozen once confirmed."""

    code = "ORDER_NOT_MODIFIABLE"


class OrderLineItemNotFound(ValidationFailed):
    code = "ORDER_LINE_ITEM_NOT_FOUND"


class EmptyOrder(BusinessRuleViolation):
    code = "EMPTY_ORDER"


class OrderAlreadyCancelled(ConflictError):
    code = "ORDER_ALREADY_CANCELLED"


class OrderAlreadyCompleted(ConflictError):
    code = "ORDER_ALREADY_COMPLETED"


class InvalidReturnLifecycleTransition(ConflictError):
    code = "INVALID_RETURN_LIFECYCLE_TRANSITION"


class ReturnWindowExpired(BusinessRuleViolation):
    code = "RETURN_WINDOW_EXPIRED"


class ReturnQuantityExceedsOrdered(ValidationFailed):
    code = "RETURN_QUANTITY_EXCEEDS_ORDERED"


class InvalidCancellationLifecycleTransition(ConflictError):
    code = "INVALID_CANCELLATION_LIFECYCLE_TRANSITION"


class CancellationQuantityExceedsOrdered(ValidationFailed):
    code = "CANCELLATION_QUANTITY_EXCEEDS_ORDERED"


class OrderNotEligibleForCancellation(BusinessRuleViolation):
    """Raised when attempting to cancel an order that has already progressed too far (e.g. already DELIVERED) -- distinct from OrderAlreadyCancelled, which covers the simpler 'already cancelled' case."""

    code = "ORDER_NOT_ELIGIBLE_FOR_CANCELLATION"


class InvalidInvoiceLifecycleTransition(ConflictError):
    code = "INVALID_INVOICE_LIFECYCLE_TRANSITION"


class InvoiceAlreadyIssued(ConflictError):
    code = "INVOICE_ALREADY_ISSUED"


class PaymentReferenceNotFound(ValidationFailed):
    code = "PAYMENT_REFERENCE_NOT_FOUND"


class FulfillmentReferenceNotFound(ValidationFailed):
    code = "FULFILLMENT_REFERENCE_NOT_FOUND"


class CurrencyMismatch(BusinessRuleViolation):
    code = "CURRENCY_MISMATCH"


class OrderEntityNotFound(ValidationFailed):
    code = "ORDER_ENTITY_NOT_FOUND"


class OrderAlreadyLocked(ConflictError):
    code = "ORDER_ALREADY_LOCKED"


class OrderNotLocked(ConflictError):
    code = "ORDER_NOT_LOCKED"


class OrderLocked(BusinessRuleViolation):
    """Raised when a mutation is attempted against a locked order -- distinct from OrderAlreadyLocked (raised by lock() itself when called twice)."""

    code = "ORDER_LOCKED"


class InvalidOrderArchivalTransition(ConflictError):
    code = "INVALID_ORDER_ARCHIVAL_TRANSITION"
