"""
Cart list/search filter parsing.

Matches Enterprise REST API Blueprint §10's uniform `filter[field]=value`
shape, per every prior module's `interfaces/api/v1/filters.py` pattern
-- plain parsing functions, no query-building logic (that stays in the
selector/repository layer).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from apps.cart.domain.enums import CartStatus, CartType
from common.exceptions import ValidationFailed

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
ALLOWED_SORT_FIELDS = {"code", "-code", "created_at", "-created_at", "updated_at", "-updated_at"}


@dataclass(frozen=True, slots=True)
class PaginationParams:
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class CartListParams:
    status: str | None
    cart_type: str | None
    customer_id: uuid.UUID | None
    is_locked: bool | None
    is_abandoned: bool | None
    is_converted: bool | None
    created_after: datetime | None
    created_before: datetime | None
    updated_after: datetime | None
    updated_before: datetime | None
    sort: str
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


def _parse_bool_flag(raw: str | None) -> bool | None:
    if raw is None:
        return None
    return raw.lower() == "true"


def _parse_datetime_flag(raw: str | None, field_name: str) -> datetime | None:
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationFailed(f"'{raw}' is not a valid ISO-8601 datetime for {field_name}.", details={"fields": [{"field": field_name, "code": "INVALID_FORMAT"}]}) from exc


def parse_uuid_param(raw: str | None, field_name: str) -> uuid.UUID | None:
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ValidationFailed(f"'{raw}' is not a valid UUID for {field_name}.", details={"fields": [{"field": field_name, "code": "INVALID_FORMAT"}]}) from exc


def parse_cart_list_params(query_params) -> CartListParams:
    page, page_size = _parse_pagination(query_params)

    status = query_params.get("filter[status]")
    if status and status not in CartStatus.values():
        raise ValidationFailed(f"'{status}' is not a valid status filter.", details={"fields": [{"field": "filter[status]", "code": "INVALID_CHOICE"}]})

    cart_type = query_params.get("filter[cart_type]")
    if cart_type and cart_type not in CartType.values():
        raise ValidationFailed(f"'{cart_type}' is not a valid cart_type filter.", details={"fields": [{"field": "filter[cart_type]", "code": "INVALID_CHOICE"}]})

    sort = query_params.get("sort", "-created_at")
    if sort not in ALLOWED_SORT_FIELDS:
        raise ValidationFailed(f"'{sort}' is not a sortable field. Allowed: {sorted(ALLOWED_SORT_FIELDS)}", details={"fields": [{"field": "sort", "code": "INVALID_CHOICE"}]})

    # "converted" is not filterable as its own boolean distinct from status=converted -- CartStatus.CONVERTED
    # already covers it, so filter[converted]=true is normalized to filter[status]=converted rather than
    # introducing a second, redundant way to express the identical query.
    is_converted = _parse_bool_flag(query_params.get("filter[converted]"))
    if is_converted:
        status = CartStatus.CONVERTED.value

    return CartListParams(
        status=status, cart_type=cart_type, customer_id=parse_uuid_param(query_params.get("filter[customer_id]"), "filter[customer_id]"),
        is_locked=_parse_bool_flag(query_params.get("filter[locked]")), is_abandoned=_parse_bool_flag(query_params.get("filter[abandoned]")),
        is_converted=is_converted, created_after=_parse_datetime_flag(query_params.get("filter[created_after]"), "filter[created_after]"),
        created_before=_parse_datetime_flag(query_params.get("filter[created_before]"), "filter[created_before]"),
        updated_after=_parse_datetime_flag(query_params.get("filter[updated_after]"), "filter[updated_after]"),
        updated_before=_parse_datetime_flag(query_params.get("filter[updated_before]"), "filter[updated_before]"),
        sort=sort, page=page, page_size=page_size,
    )
