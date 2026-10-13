"""
Ordering pagination parameter shapes.

A thin, Ordering-specific naming layer over the same page/page_size
parsing every prior module already uses (see `filters.py::
_parse_pagination`) -- this file exists because this phase's brief
explicitly names two distinct shapes (customer-facing vs. admin), not
because the underlying mechanics differ from Cart's or Pricing's.
Neither class builds its own query or paginator; both are plain
parameter holders consumed by views.py, which still calls
`common.responses.paginated_response()` for the actual envelope,
matching every prior module.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
ADMIN_DEFAULT_PAGE_SIZE = 50
ADMIN_MAX_PAGE_SIZE = 200


@dataclass(frozen=True, slots=True)
class OrderingPagination:
    """Customer-facing pagination -- smaller default/max page sizes, since a customer's own order list is rarely large."""

    page: int
    page_size: int

    @staticmethod
    def from_query_params(query_params) -> "OrderingPagination":
        from common.exceptions import ValidationFailed

        try:
            page = max(int(query_params.get("page", 1)), 1)
            page_size = min(max(int(query_params.get("page_size", DEFAULT_PAGE_SIZE)), 1), MAX_PAGE_SIZE)
        except ValueError as exc:
            raise ValidationFailed("page/page_size must be integers.") from exc
        return OrderingPagination(page=page, page_size=page_size)


@dataclass(frozen=True, slots=True)
class AdminOrderingPagination:
    """Admin/staff pagination -- larger default/max page sizes, since admin tooling routinely needs to page through hundreds of orders."""

    page: int
    page_size: int

    @staticmethod
    def from_query_params(query_params) -> "AdminOrderingPagination":
        from common.exceptions import ValidationFailed

        try:
            page = max(int(query_params.get("page", 1)), 1)
            page_size = min(max(int(query_params.get("page_size", ADMIN_DEFAULT_PAGE_SIZE)), 1), ADMIN_MAX_PAGE_SIZE)
        except ValueError as exc:
            raise ValidationFailed("page/page_size must be integers.") from exc
        return AdminOrderingPagination(page=page, page_size=page_size)
