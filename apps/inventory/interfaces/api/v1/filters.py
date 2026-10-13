"""
Inventory list/search filter parsing.

Matches Enterprise REST API Blueprint §10's uniform `filter[field]=value`
shape, per every prior module's `interfaces/api/v1/filters.py` pattern
-- plain parsing functions, no query-building logic (that stays in the
selector/repository layer).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from apps.inventory.domain.enums import InventoryStatus, StockStatus
from common.exceptions import ValidationFailed

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
ALLOWED_SORT_FIELDS = {"code", "-code", "created_at", "-created_at", "updated_at", "-updated_at"}


@dataclass(frozen=True, slots=True)
class PaginationParams:
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class InventoryListParams:
    status: str | None
    query: str | None
    sort: str
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class StockFilterParams:
    warehouse_id: uuid.UUID | None
    shelf_id: uuid.UUID | None
    stock_status: str | None
    page: int
    page_size: int


def _parse_pagination(query_params) -> tuple[int, int]:
    try:
        page = max(int(query_params.get("page", 1)), 1)
        page_size = min(max(int(query_params.get("page_size", DEFAULT_PAGE_SIZE)), 1), MAX_PAGE_SIZE)
    except ValueError as exc:
        raise ValidationFailed("page/page_size must be integers.") from exc
    return page, page_size


def parse_pagination(query_params) -> PaginationParams:
    page, page_size = _parse_pagination(query_params)
    return PaginationParams(page=page, page_size=page_size)


def parse_uuid_param(raw: str | None, field_name: str) -> uuid.UUID | None:
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ValidationFailed(f"'{raw}' is not a valid UUID for {field_name}.", details={"fields": [{"field": field_name, "code": "INVALID_FORMAT"}]}) from exc


def parse_inventory_list_params(query_params) -> InventoryListParams:
    page, page_size = _parse_pagination(query_params)
    status = query_params.get("filter[status]")
    if status and status not in InventoryStatus.values():
        raise ValidationFailed(f"'{status}' is not a valid status filter.", details={"fields": [{"field": "filter[status]", "code": "INVALID_CHOICE"}]})

    sort = query_params.get("sort", "-created_at")
    if sort not in ALLOWED_SORT_FIELDS:
        raise ValidationFailed(f"'{sort}' is not a sortable field. Allowed: {sorted(ALLOWED_SORT_FIELDS)}", details={"fields": [{"field": "sort", "code": "INVALID_CHOICE"}]})

    return InventoryListParams(status=status, query=query_params.get("q"), sort=sort, page=page, page_size=page_size)


def parse_stock_filter_params(query_params) -> StockFilterParams:
    page, page_size = _parse_pagination(query_params)
    stock_status = query_params.get("filter[stock_status]")
    if stock_status and stock_status not in StockStatus.values():
        raise ValidationFailed(f"'{stock_status}' is not a valid stock_status filter.", details={"fields": [{"field": "filter[stock_status]", "code": "INVALID_CHOICE"}]})

    return StockFilterParams(
        warehouse_id=parse_uuid_param(query_params.get("filter[warehouse_id]"), "filter[warehouse_id]"),
        shelf_id=parse_uuid_param(query_params.get("filter[shelf_id]"), "filter[shelf_id]"),
        stock_status=stock_status, page=page, page_size=page_size,
    )


def parse_expiring_batches_params(query_params) -> int:
    raw = query_params.get("within_days", "30")
    try:
        within_days = int(raw)
    except ValueError as exc:
        raise ValidationFailed("within_days must be an integer.") from exc
    if within_days <= 0:
        raise ValidationFailed("within_days must be positive.")
    return within_days
