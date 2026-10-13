"""
Reviews domain events.

**A deliberate scope decision, disclosed rather than silently
assumed**: no `ReviewDeleted` event is defined, despite being listed
as a "potential example" in this phase's own brief. This module's
aggregate design uses a soft, reversible-in-principle customer-
initiated `WITHDRAWN` status (matching the soft-deletion/append-only
conventions established throughout this build) rather than a hard
delete -- `ReviewWithdrawn` is the accurate name for what actually
happens; `ReviewDeleted` would misdescribe a status change as a hard
deletion, which this module's Domain never performs.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ReviewCreated:
    review_id: uuid.UUID
    product_id: uuid.UUID
    customer_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"review_id": str(self.review_id), "product_id": str(self.product_id), "customer_id": str(self.customer_id)}


@dataclass(frozen=True, slots=True)
class ReviewSubmitted:
    review_id: uuid.UUID
    product_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"review_id": str(self.review_id), "product_id": str(self.product_id)}


@dataclass(frozen=True, slots=True)
class ReviewApproved:
    review_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"review_id": str(self.review_id)}


@dataclass(frozen=True, slots=True)
class ReviewRejected:
    review_id: uuid.UUID
    reason: str

    def to_payload(self) -> dict:
        return {**asdict(self), "review_id": str(self.review_id)}


@dataclass(frozen=True, slots=True)
class ReviewPublished:
    review_id: uuid.UUID
    product_id: uuid.UUID
    rating: int

    def to_payload(self) -> dict:
        return {**asdict(self), "review_id": str(self.review_id), "product_id": str(self.product_id)}


@dataclass(frozen=True, slots=True)
class ReviewHidden:
    review_id: uuid.UUID
    reason: str

    def to_payload(self) -> dict:
        return {**asdict(self), "review_id": str(self.review_id)}


@dataclass(frozen=True, slots=True)
class ReviewEdited:
    review_id: uuid.UUID
    reset_to_pending_moderation: bool

    def to_payload(self) -> dict:
        return {**asdict(self), "review_id": str(self.review_id)}


@dataclass(frozen=True, slots=True)
class ReviewWithdrawn:
    review_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"review_id": str(self.review_id)}


@dataclass(frozen=True, slots=True)
class ReviewMediaAttached:
    review_id: uuid.UUID
    media_id: uuid.UUID
    media_type: str

    def to_payload(self) -> dict:
        return {**asdict(self), "review_id": str(self.review_id), "media_id": str(self.media_id)}
