from __future__ import annotations

from common.exceptions import ConflictError, ResourceNotFound


class PaymentNotFound(ResourceNotFound):
    code = "PAYMENT_NOT_FOUND"


class InvalidPaymentTransition(ConflictError):
    """Rejects an illegal PaymentStatus transition -- e.g. a webhook reporting success for an already-failed or already-succeeded payment."""

    code = "INVALID_PAYMENT_TRANSITION"


class PaymentAmountMismatch(ConflictError):
    """The provider/webhook-reported amount does not match this Payment's own authoritative, server-derived amount -- rejected, never silently accepted."""

    code = "PAYMENT_AMOUNT_MISMATCH"


class OrderNotPayable(ConflictError):
    """The Order is not in a state that legitimately allows a new payment attempt (e.g. already confirmed, or has no priced line items)."""

    code = "ORDER_NOT_PAYABLE"
