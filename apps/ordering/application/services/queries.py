"""
Query Application Services: SearchOrders, AdminListOrders,
ListCustomerOrders, GetOrderSummary.
"""
from __future__ import annotations

import uuid

from apps.ordering.application.ports import OrderReadRepository, OrderRepository, OrderSearchGateway
from apps.ordering.domain.aggregates import Order
from common.exceptions import ResourceNotFound


class SearchOrders:
    def __init__(self, search_gateway: OrderSearchGateway) -> None:
        self._search_gateway = search_gateway

    def execute(self, query: str, filters: dict, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        return self._search_gateway.search(query=query, filters=filters, page=page, page_size=page_size)


class AdminListOrders:
    def __init__(self, repo: OrderRepository) -> None:
        self._repo = repo

    def execute(self, status: str | None = None, page: int = 1, page_size: int = 20) -> tuple[list[Order], int]:
        return self._repo.list_for_admin(status=status, page=page, page_size=page_size)


class ListCustomerOrders:
    def __init__(self, repo: OrderRepository) -> None:
        self._repo = repo

    def execute(self, customer_id: uuid.UUID, status: str | None = None, page: int = 1, page_size: int = 20) -> tuple[list[Order], int]:
        return self._repo.list_for_customer(customer_id, status=status, page=page, page_size=page_size)


class GetOrderSummary:
    """CQRS read side -- backed by `OrderReadRepository`, distinct from `LoadOrder` (lifecycle.py), which reconstructs the full write-side aggregate."""

    def __init__(self, read_repo: OrderReadRepository) -> None:
        self._read_repo = read_repo

    def execute(self, order_id: uuid.UUID) -> dict:
        summary = self._read_repo.get_summary(order_id)
        if summary is None:
            raise ResourceNotFound("Order not found.")
        return summary
