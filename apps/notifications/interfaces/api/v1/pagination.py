"""
Notifications pagination parameter shape.

Matches the exact `ChatPagination`/`ReviewPagination` offset-based
(page/page_size) shape already established across the platform -- no
new pagination style invented. Only one class exists -- no admin-
scoped variant, since no admin-facing listing endpoint exists this
phase (no equivalent to `ConversationRepository.list_unassigned` was
ever certified for Notifications).
"""
from __future__ import annotations

from dataclasses import dataclass

from common.exceptions import ValidationFailed

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class NotificationPagination:
    page: int
    page_size: int

    @staticmethod
    def from_query_params(query_params) -> "NotificationPagination":
        try:
            page = max(int(query_params.get("page", 1)), 1)
            page_size = min(max(int(query_params.get("page_size", DEFAULT_PAGE_SIZE)), 1), MAX_PAGE_SIZE)
        except ValueError as exc:
            raise ValidationFailed("page/page_size must be integers.") from exc
        return NotificationPagination(page=page, page_size=page_size)
