"""
Pagination classes (Enterprise REST API Blueprint §8).

Two strategies, never mixed within one endpoint:
  - StandardPageNumberPagination: UI-paginated collections (Catalog,
    Orders, Reviews, most Admin CRM list views).
  - StandardCursorPagination: high-volume, append-only, real-time
    collections (chat.messages, notifications, wallet ledger,
    audit.activity_timeline, analytics time series).

Both render through common/responses/envelope.py's paginated_response
shape -- a view selects one of these `pagination_class` values and the
envelope is built automatically by common/responses' base viewset (see
common/serializers/base.py docstring for the wiring point).
"""
from __future__ import annotations

from typing import Any

from rest_framework.pagination import CursorPagination, PageNumberPagination

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class StandardPageNumberPagination(PageNumberPagination):
    page_size = DEFAULT_PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = MAX_PAGE_SIZE
    page_query_param = "page"

    def get_paginated_meta(self) -> dict[str, Any]:
        return {
            "strategy": "page",
            "page": self.page.number,
            "page_size": self.get_page_size(self.request),
            "total_pages": self.page.paginator.num_pages,
            "total_count": self.page.paginator.count,
        }


class StandardCursorPagination(CursorPagination):
    page_size = DEFAULT_PAGE_SIZE
    max_page_size = MAX_PAGE_SIZE
    page_size_query_param = "limit"
    cursor_query_param = "cursor"
    ordering = "-created_at"

    def get_paginated_meta(self) -> dict[str, Any]:
        return {
            "strategy": "cursor",
            "next_cursor": self.get_next_link(),
            "has_more": self.has_next,
        }
