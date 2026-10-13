"""
Notifications list filter parsing.

**Every filter here is derived strictly from the actual, certified
selector signature re-verified in this phase's own Step 1**
(`NotificationSelector.list_for_recipient(recipient_id, status, page,
page_size)`) -- not invented from generic REST assumptions. Only
`status` is exposed, since that is the only filter parameter the
selector actually accepts. No `notification_type`/`priority` filter
exists, despite being listed as "potential legitimate filters" in
this phase's own brief -- the real selector does not support them,
and this phase's own rules explicitly forbid adding a filter merely
because a field exists ("do not add filters merely because fields
exist").
"""
from __future__ import annotations

from dataclasses import dataclass

from apps.notifications.domain.enums import NotificationStatus
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


@dataclass(frozen=True, slots=True)
class NotificationListParams:
    status: str | None
    page: int
    page_size: int


def parse_notification_list_params(query_params) -> NotificationListParams:
    page, page_size = _parse_pagination(query_params)
    status = query_params.get("filter[status]")
    if status and status not in NotificationStatus.values():
        raise ValidationFailed(f"'{status}' is not a valid status filter.", details={"fields": [{"field": "filter[status]", "code": "INVALID_CHOICE"}]})
    return NotificationListParams(status=status, page=page, page_size=page_size)
