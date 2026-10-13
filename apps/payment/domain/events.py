from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class PaymentCreated:
    payment_id: uuid.UUID
    order_id: uuid.UUID
    amount: str
    currency: str

    def to_payload(self) -> dict:
        return {**asdict(self), "payment_id": str(self.payment_id), "order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class PaymentSucceeded:
    payment_id: uuid.UUID
    order_id: uuid.UUID
    amount: str
    currency: str

    def to_payload(self) -> dict:
        return {**asdict(self), "payment_id": str(self.payment_id), "order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class PaymentFailed:
    payment_id: uuid.UUID
    order_id: uuid.UUID
    reason: str

    def to_payload(self) -> dict:
        return {**asdict(self), "payment_id": str(self.payment_id), "order_id": str(self.order_id)}


@dataclass(frozen=True, slots=True)
class PaymentAudited:
    """A lightweight, real audit trail record -- deliberately NOT built on the generic AuditEvent/AuditEventBuilder (which is purely functional and never actually persists anything unless its return value is explicitly staged -- a real, confirmed no-op pattern found elsewhere in this codebase, e.g. Ordering's own AttachShipment). This event is genuinely staged to the outbox, giving Payment mutations a real, queryable audit trail."""

    payment_id: uuid.UUID
    action: str
    before_status: str
    after_status: str

    def to_payload(self) -> dict:
        return {**asdict(self), "payment_id": str(self.payment_id)}


@dataclass(frozen=True, slots=True)
class PaymentCancelled:
    payment_id: uuid.UUID
    order_id: uuid.UUID

    def to_payload(self) -> dict:
        return {**asdict(self), "payment_id": str(self.payment_id), "order_id": str(self.order_id)}
