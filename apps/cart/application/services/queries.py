"""
Query Application Services: GetCart, ListCustomerCarts, SearchCart,
GetSnapshotHistory.
"""
from __future__ import annotations

import uuid

from apps.cart.application.ports import CartRepository, CartSearchGateway
from apps.cart.domain.aggregates import Cart
from common.exceptions import ResourceNotFound


class GetCart:
    def __init__(self, repo: CartRepository) -> None:
        self._repo = repo

    def execute(self, cart_id: uuid.UUID) -> Cart:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        return cart


class ListCustomerCarts:
    def __init__(self, repo: CartRepository) -> None:
        self._repo = repo

    def execute(self, customer_id: uuid.UUID, status: str | None = None, page: int = 1, page_size: int = 20) -> tuple[list[Cart], int]:
        return self._repo.list_for_customer(customer_id, status=status, page=page, page_size=page_size)


class SearchCart:
    def __init__(self, search_gateway: CartSearchGateway) -> None:
        self._search_gateway = search_gateway

    def execute(self, query: str, filters: dict, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        return self._search_gateway.search(query=query, filters=filters, page=page, page_size=page_size)


class GetSnapshotHistory:
    def __init__(self, repo: CartRepository) -> None:
        self._repo = repo

    def execute(self, cart_id: uuid.UUID) -> list:
        cart = self._repo.get_by_id(cart_id)
        if cart is None:
            raise ResourceNotFound("Cart not found.")
        return sorted(cart.snapshots.values(), key=lambda s: s.captured_at, reverse=True)


class AdminListCarts:
    """Not in this phase's explicit 25-service name list verbatim, but required to make 'admin listing across all carts' (as opposed to one customer's carts, which ListCustomerCarts already covers) reachable -- the same category of small, justified addition already made in every prior module (e.g. Store's AdminListStores, Inventory's AdminListInventory)."""

    def __init__(self, repo: CartRepository) -> None:
        self._repo = repo

    def execute(self, status: str | None = None, cart_type: str | None = None, page: int = 1, page_size: int = 20) -> tuple[list[Cart], int]:
        return self._repo.list_for_admin(status=status, cart_type=cart_type, page=page, page_size=page_size)
