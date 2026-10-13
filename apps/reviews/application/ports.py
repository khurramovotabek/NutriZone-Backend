"""
Application-layer port (abstract interface) for Reviews.

**A disclosed, minimal exception, per this phase's own explicit
instruction**: this file's brief requires Infrastructure's repository
to fulfill a Port, and every prior module in this build (Wallet,
Loyalty, Ordering, Fulfillment) places Ports in `application/ports.py`,
never in `infrastructure/`. Rather than either violate that
established convention or leave the repository with nothing to
formally implement, this single Protocol interface -- zero business
logic, zero Application Services, zero service context -- is the
smallest artifact that bridges the gap. Nothing else in `application/`
was touched this phase. Matches the identical, already-established
precedent from Loyalty's Phase 2.
"""
from __future__ import annotations

import uuid
from typing import Protocol

from apps.reviews.domain.aggregates import Review


class ReviewRepository(Protocol):
    def get_by_id(self, review_id: uuid.UUID) -> Review | None: ...

    def list_for_product(self, product_id: uuid.UUID, status: str | None, page: int, page_size: int) -> tuple[list[Review], int]: ...

    def list_for_customer(self, customer_id: uuid.UUID, page: int, page_size: int) -> tuple[list[Review], int]: ...

    def save(self, review: Review) -> Review: ...

    def list_for_admin(self, status: str | None, page: int, page_size: int) -> tuple[list[Review], int]: ...
