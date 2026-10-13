from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from common.exceptions import ValidationFailed
from common.utils import DomainStrEnum


class PaymentStatus(DomainStrEnum):
    """
    Minimal, justified lifecycle -- only states with a real, distinct
    meaning for this project's actual flow (server creates a payment
    attempt, hands off to a provider/test gateway, receives a
    callback). No PARTIALLY_REFUNDED here: refund is explicitly out
    of this phase's scope (confirmed absent anywhere in the
    repository) -- adding a state for an unbuilt capability would be
    speculative, not justified by real behavior.
    """

    CREATED = "created"
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    # Payme/Uzum can cancel an already-performed transaction (a refund); recorded, never initiated by the shop itself.
    REFUNDED = "refunded"


_LEGAL_TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
    PaymentStatus.CREATED: {PaymentStatus.PENDING, PaymentStatus.CANCELLED, PaymentStatus.FAILED},
    PaymentStatus.PENDING: {PaymentStatus.SUCCEEDED, PaymentStatus.FAILED, PaymentStatus.CANCELLED},
    PaymentStatus.SUCCEEDED: {PaymentStatus.REFUNDED},  # only a provider-side cancellation of a performed transaction
    PaymentStatus.REFUNDED: set(),  # terminal
    PaymentStatus.FAILED: set(),  # terminal
    PaymentStatus.CANCELLED: set(),  # terminal
}


def is_legal_transition(current: PaymentStatus, target: PaymentStatus) -> bool:
    return target in _LEGAL_TRANSITIONS.get(current, set())


@dataclass(frozen=True, slots=True)
class PaymentAmount:
    """A frozen, validated (amount, currency) pair -- the payment's own authoritative charge amount, always derived server-side from the Order's real line items, never accepted from a client."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if self.amount <= 0:
            raise ValidationFailed("Payment amount must be positive.")
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValidationFailed("Payment currency must be a 3-letter uppercase ISO code.")
