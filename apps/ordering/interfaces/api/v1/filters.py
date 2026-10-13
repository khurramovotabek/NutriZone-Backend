"""
Ordering list/search filter parsing.

Matches Enterprise REST API Blueprint §10's uniform `filter[field]=value`
shape, per every prior module's `interfaces/api/v1/filters.py` pattern
-- plain parsing functions, no query-building logic (that stays in the
selector/repository layer).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from apps.ordering.domain.enums import OrderStatus
from common.exceptions import ValidationFailed

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
ALLOWED_SORT_FIELDS = {"order_number", "-order_number", "created_at", "-created_at", "updated_at", "-updated_at"}


def _parse_pagination(query_params) -> tuple[int, int]:
    try:
        page = max(int(query_params.get("page", 1)), 1)
        page_size = min(max(int(query_params.get("page_size", DEFAULT_PAGE_SIZE)), 1), MAX_PAGE_SIZE)
    except ValueError as exc:
        raise ValidationFailed("page/page_size must be integers.") from exc
    return page, page_size


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


@dataclass(frozen=True, slots=True)
class OrderListParams:
    status: str | None
    customer_id: uuid.UUID | None
    order_number: str | None
    is_archived: bool | None
    is_locked: bool | None
    has_invoice: bool | None
    payment_id: uuid.UUID | None
    fulfillment_id: uuid.UUID | None
    created_after: datetime | None
    created_before: datetime | None
    updated_after: datetime | None
    updated_before: datetime | None
    completed_after: datetime | None
    cancelled_after: datetime | None
    sort: str
    page: int
    page_size: int


def parse_order_list_params(query_params) -> OrderListParams:
    page, page_size = _parse_pagination(query_params)

    status = query_params.get("filter[status]")
    if status and status not in OrderStatus.values():
        raise ValidationFailed(f"'{status}' is not a valid status filter.", details={"fields": [{"field": "filter[status]", "code": "INVALID_CHOICE"}]})

    sort = query_params.get("sort", "-created_at")
    if sort not in ALLOWED_SORT_FIELDS:
        raise ValidationFailed(f"'{sort}' is not a sortable field. Allowed: {sorted(ALLOWED_SORT_FIELDS)}", details={"fields": [{"field": "sort", "code": "INVALID_CHOICE"}]})

    # "completed"/"cancelled" boolean flags normalize to filter[status]=<value> rather than introducing
    # a second, redundant way to express the identical query -- same pattern as Cart's filter[converted].
    is_completed = _parse_bool_flag(query_params.get("filter[completed]"))
    is_cancelled = _parse_bool_flag(query_params.get("filter[cancelled]"))
    if is_completed:
        status = OrderStatus.COMPLETED.value
    elif is_cancelled:
        status = OrderStatus.CANCELLED.value

    return OrderListParams(
        status=status, customer_id=parse_uuid_param(query_params.get("filter[customer_id]"), "filter[customer_id]"),
        order_number=query_params.get("filter[order_number]"), is_archived=_parse_bool_flag(query_params.get("filter[archived]")),
        is_locked=_parse_bool_flag(query_params.get("filter[locked]")), has_invoice=_parse_bool_flag(query_params.get("filter[invoice]")),
        payment_id=parse_uuid_param(query_params.get("filter[payment_id]"), "filter[payment_id]"),
        fulfillment_id=parse_uuid_param(query_params.get("filter[fulfillment_id]"), "filter[fulfillment_id]"),
        created_after=_parse_datetime_flag(query_params.get("filter[created_after]"), "filter[created_after]"),
        created_before=_parse_datetime_flag(query_params.get("filter[created_before]"), "filter[created_before]"),
        updated_after=_parse_datetime_flag(query_params.get("filter[updated_after]"), "filter[updated_after]"),
        updated_before=_parse_datetime_flag(query_params.get("filter[updated_before]"), "filter[updated_before]"),
        completed_after=_parse_datetime_flag(query_params.get("filter[completed_after]"), "filter[completed_after]"),
        cancelled_after=_parse_datetime_flag(query_params.get("filter[cancelled_after]"), "filter[cancelled_after]"),
        sort=sort, page=page, page_size=page_size,
    )
