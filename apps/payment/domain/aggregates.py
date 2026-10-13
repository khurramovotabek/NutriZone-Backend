from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from apps.payment.domain.events import PaymentCancelled, PaymentCreated, PaymentFailed, PaymentSucceeded
from apps.payment.domain.exceptions import InvalidPaymentTransition
from apps.payment.domain.value_objects import PaymentAmount, PaymentStatus, is_legal_transition


@dataclass(slots=True)
class Payment:
    """
    Aggregate root. One Payment represents one logical charge attempt
    against one Order. `provider_reference` is the external
    transaction identifier reported by the provider/gateway -- kept
    separate from `id` (this aggregate's own internal identity),
    matching this phase's own explicit requirement to never conflate
    the two. Real amount/currency are set once at creation from the
    Order's own certified line-item data and never change afterward.
    """

    id: uuid.UUID
    order_id: uuid.UUID
    customer_id: uuid.UUID
    amount: PaymentAmount
    provider: str
    status: PaymentStatus = PaymentStatus.CREATED
    provider_reference: str | None = None
    failure_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @staticmethod
    def create(payment_id: uuid.UUID, order_id: uuid.UUID, customer_id: uuid.UUID, amount: PaymentAmount, provider: str, at: datetime) -> tuple["Payment", PaymentCreated]:
        payment = Payment(id=payment_id, order_id=order_id, customer_id=customer_id, amount=amount, provider=provider, status=PaymentStatus.CREATED, created_at=at, updated_at=at)
        event = PaymentCreated(payment_id=payment_id, order_id=order_id, amount=str(amount.amount), currency=amount.currency)
        return payment, event

    def mark_pending(self, provider_reference: str, at: datetime) -> None:
        self._transition(PaymentStatus.PENDING, at)
        self.provider_reference = provider_reference

    def mark_succeeded(self, at: datetime) -> PaymentSucceeded:
        self._transition(PaymentStatus.SUCCEEDED, at)
        return PaymentSucceeded(payment_id=self.id, order_id=self.order_id, amount=str(self.amount.amount), currency=self.amount.currency)

    def mark_failed(self, reason: str, at: datetime) -> PaymentFailed:
        self._transition(PaymentStatus.FAILED, at)
        self.failure_reason = reason
        return PaymentFailed(payment_id=self.id, order_id=self.order_id, reason=reason)

    def mark_cancelled(self, at: datetime) -> PaymentCancelled:
        self._transition(PaymentStatus.CANCELLED, at)
        return PaymentCancelled(payment_id=self.id, order_id=self.order_id)

    def _transition(self, target: PaymentStatus, at: datetime) -> None:
        if not is_legal_transition(self.status, target):
            raise InvalidPaymentTransition(f"Cannot transition payment from {self.status.value} to {target.value}.")
        self.status = target
        self.updated_at = at
