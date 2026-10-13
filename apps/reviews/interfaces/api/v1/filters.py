"""
Reviews list/search filter parsing.

**Every filter here is derived strictly from the actual, certified
selector/repository signatures re-verified in this phase's own Step
1** (`ReviewSelector.list_for_product(product_id, status, page,
page_size)`, `ReviewSelector.list_for_customer(customer_id, page,
page_size)`, `DjangoReviewRepository.list_for_admin(status, page,
page_size)`) -- not invented from generic REST assumptions. No
`rating` or `date range` filter is exposed, because no certified
selector accepts one; adding query-parameter parsing for a filter
with no backend implementation would be exactly the "pretend it
works" behavior this phase's own rules forbid. No `search`/`q`
parameter exists anywhere in this file for the same reason -- there
is no free-text search capability in any certified selector to fold
it into, so unlike Loyalty's precedent (which had a real, if
unconsumed, `search` field), Reviews' filters omit it entirely rather
than exposing a parameter that would silently do nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

from apps.reviews.domain.enums import ReviewStatus
from common.exceptions import ValidationFailed

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def _parse_pagination(query_params) -> tuple[int, int]:
    try:
        page = max(int(query_params.get("page", 1)), 1)
        page_size = min(max(int(query_params.get("page_size", DEFAULT_PAGE_SIZE)), 1), MAX_PAGE_SIZE)
    except ValueError as exc:
        raise ValidationFailed("page/page_size must be integers.") from exc
    return page, page_size


def _validate_status(status: str | None) -> str | None:
    if status and status not in ReviewStatus.values():
        raise ValidationFailed(f"'{status}' is not a valid status filter.", details={"fields": [{"field": "filter[status]", "code": "INVALID_CHOICE"}]})
    return status


@dataclass(frozen=True, slots=True)
class ProductReviewListParams:
    """Backs `ReviewSelector.list_for_product` exactly."""

    status: str | None
    page: int
    page_size: int


def parse_product_review_list_params(query_params) -> ProductReviewListParams:
    page, page_size = _parse_pagination(query_params)
    return ProductReviewListParams(status=_validate_status(query_params.get("filter[status]")), page=page, page_size=page_size)


@dataclass(frozen=True, slots=True)
class CustomerReviewListParams:
    """Backs `ReviewSelector.list_for_customer` exactly -- no status filter, since the selector method itself accepts none."""

    page: int
    page_size: int


def parse_customer_review_list_params(query_params) -> CustomerReviewListParams:
    page, page_size = _parse_pagination(query_params)
    return CustomerReviewListParams(page=page, page_size=page_size)


@dataclass(frozen=True, slots=True)
class AdminReviewListParams:
    """Backs `DjangoReviewRepository.list_for_admin` exactly."""

    status: str | None
    page: int
    page_size: int


def parse_admin_review_list_params(query_params) -> AdminReviewListParams:
    page, page_size = _parse_pagination(query_params)
    return AdminReviewListParams(status=_validate_status(query_params.get("filter[status]")), page=page, page_size=page_size)
