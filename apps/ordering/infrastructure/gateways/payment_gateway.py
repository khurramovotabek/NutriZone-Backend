"""
PaymentGateway -- Anti-Corruption Layer interface for a future
Payments/Wallet module.

Ordering NEVER executes payment itself (per this module's explicit
functional scope). This gateway exists so a future Payments module
can be wired in through composition.py without Ordering's Application
layer ever importing that module's domain -- Interfaces only, no
business logic, ready for future implementation.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Protocol


class PaymentGateway(Protocol):
    """
    Read-only status-check interface -- Ordering asks "what is the
    status of payment X" (to reconcile `OrderPaymentReference`), it
    never asks a gateway to "charge this amount." Initiating payment
    is a future Payments module's own responsibility, triggered by
    that module reacting to Ordering's own `OrderCreated`/
    `OrderConfirmed` events via the Outbox -- not by Ordering calling
    out synchronously.
    """

    def get_payment_status(self, payment_id: uuid.UUID) -> str | None: ...


class NotImplementedPaymentGateway:
    """Default composition-root binding until a real Payments module exists -- fails loudly and explicitly rather than silently pretending to succeed."""

    def get_payment_status(self, payment_id: uuid.UUID) -> str | None:
        raise NotImplementedError("No Payments module is registered yet. PaymentGateway is a placeholder interface, per this phase's explicit scope.")
