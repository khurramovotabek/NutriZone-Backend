"""
Application-layer ports (abstract interfaces) for Ordering.

Matches the pattern established by every prior module's
application/ports.py. Three repository Ports for the three aggregate
roots, plus a CQRS read-side split (`OrderReadRepository`) since
Order listing/search is a genuinely separate, denormalized-friendly
concern from the write-side `OrderRepository`.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from apps.ordering.domain.aggregates import Order, OrderCancellation, OrderReturn


class OrderRepository(Protocol):
    def get_by_id(self, order_id: uuid.UUID) -> Order | None: ...

    def get_by_order_number(self, order_number: str) -> Order | None: ...

    def get_by_cart_id(self, cart_id: uuid.UUID) -> Order | None: ...

    def save(self, order: Order) -> Order: ...

    def list_for_customer(self, customer_id: uuid.UUID, status: str | None, page: int, page_size: int) -> tuple[list[Order], int]: ...

    def list_expiring_before(self, at: datetime) -> list[Order]: ...

    def list_for_admin(self, status: str | None, page: int, page_size: int) -> tuple[list[Order], int]: ...


class OrderReadRepository(Protocol):
    """CQRS read side -- denormalized, list/search-optimized order lookups, kept separate from the write-side `OrderRepository` since a listing view rarely needs the full aggregate graph reconstructed."""

    def get_summary(self, order_id: uuid.UUID) -> dict | None: ...

    def search(self, query: str, filters: dict, page: int, page_size: int) -> tuple[list[dict], int]: ...


class OrderReturnRepository(Protocol):
    def get_by_id(self, return_id: uuid.UUID) -> OrderReturn | None: ...

    def get_by_return_number(self, return_number: str) -> OrderReturn | None: ...

    def list_for_order(self, order_id: uuid.UUID) -> list[OrderReturn]: ...

    def save(self, order_return: OrderReturn) -> OrderReturn: ...


class OrderCancellationRepository(Protocol):
    def get_by_id(self, cancellation_id: uuid.UUID) -> OrderCancellation | None: ...

    def list_for_order(self, order_id: uuid.UUID) -> list[OrderCancellation]: ...

    def save(self, cancellation: OrderCancellation) -> OrderCancellation: ...


class OrderSearchGateway(Protocol):
    """Anti-Corruption Layer boundary for order search (admin/support tooling) -- same launch-stage Postgres-backed approach as every other module's search backend."""

    def search(self, query: str, filters: dict, page: int, page_size: int) -> tuple[list[dict], int]: ...
