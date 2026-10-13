"""
Reviews pagination parameter shapes.

Matches the exact `WalletPagination`/`AdminWalletPagination` and
`LoyaltyPagination`/`AdminLoyaltyPagination` naming and offset-based
(page/page_size) shape already established across the platform -- no
new pagination style invented, per this phase's explicit instruction.
"""
from __future__ import annotations

from dataclasses import dataclass

from common.exceptions import ValidationFailed

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
ADMIN_DEFAULT_PAGE_SIZE = 50
ADMIN_MAX_PAGE_SIZE = 200


def _parse(query_params, default_size: int, max_size: int) -> tuple[int, int]:
    try:
        page = max(int(query_params.get("page", 1)), 1)
        page_size = min(max(int(query_params.get("page_size", default_size)), 1), max_size)
    except ValueError as exc:
        raise ValidationFailed("page/page_size must be integers.") from exc
    return page, page_size


@dataclass(frozen=True, slots=True)
class ReviewPagination:
    """Customer/public-facing pagination -- matches `WalletPagination`/`LoyaltyPagination`'s exact shape."""

    page: int
    page_size: int

    @staticmethod
    def from_query_params(query_params) -> "ReviewPagination":
        page, page_size = _parse(query_params, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE)
        return ReviewPagination(page=page, page_size=page_size)


@dataclass(frozen=True, slots=True)
class AdminReviewPagination:
    """Admin/staff pagination -- matches `AdminWalletPagination`/`AdminLoyaltyPagination`'s exact shape."""

    page: int
    page_size: int

    @staticmethod
    def from_query_params(query_params) -> "AdminReviewPagination":
        page, page_size = _parse(query_params, ADMIN_DEFAULT_PAGE_SIZE, ADMIN_MAX_PAGE_SIZE)
        return AdminReviewPagination(page=page, page_size=page_size)
