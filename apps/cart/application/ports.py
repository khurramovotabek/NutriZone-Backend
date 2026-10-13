"""
Application-layer ports (abstract interfaces) for Cart.

Matches the pattern established by every prior module's
application/ports.py. Cross-cutting ports (Cache/Audit/Metrics/Outbox/
Clock/Health) are consumed directly from `core/`, not redeclared.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from apps.cart.domain.aggregates import Cart


class CartRepository(Protocol):
    def get_by_id(self, cart_id: uuid.UUID) -> Cart | None: ...

    def get_by_code(self, code: str) -> Cart | None:
        """Added during Phase 3 (Interfaces) as a minimum-necessary fix -- every required endpoint in this phase's brief uses {code} as the URL identifier, but this Port originally had no way to resolve one. See the Phase 3 certification report's Step 1-equivalent inconsistency writeup for the full explanation."""
        ...

    def get_by_token(self, token: str) -> Cart | None: ...

    def get_active_for_customer(self, customer_id: uuid.UUID) -> Cart | None: ...

    def save(self, cart: Cart) -> Cart: ...

    def delete(self, cart_id: uuid.UUID) -> None: ...

    def list_for_customer(self, customer_id: uuid.UUID, status: str | None, page: int, page_size: int) -> tuple[list[Cart], int]: ...

    def list_expiring_before(self, at: datetime) -> list[Cart]: ...

    def list_for_admin(self, status: str | None, cart_type: str | None, page: int, page_size: int) -> tuple[list[Cart], int]: ...


class CartSearchGateway(Protocol):
    """Anti-Corruption Layer boundary for cart search (admin/support tooling) -- same launch-stage Postgres-backed approach as every other module's search backend."""

    def search(self, query: str, filters: dict, page: int, page_size: int) -> tuple[list[dict], int]: ...
