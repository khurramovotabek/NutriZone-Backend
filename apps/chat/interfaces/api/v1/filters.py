"""
Chat list filter parsing.

**Every filter here is derived strictly from the actual, certified
selector signatures re-verified in this phase's own Step 1**
(`ConversationSelector.list_for_user(user_id, status, page,
page_size)`) -- not invented from generic REST assumptions. No
`conversation_type` filter is exposed on the user-conversation-list
endpoint, since that selector method does not accept one.
`MessageSelector.list_for_conversation` accepts no filter beyond
pagination, so no `MessageListParams` class exists at all -- only
pagination applies to that endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass

from apps.chat.domain.enums import ConversationStatus
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
class ConversationListParams:
    """Backs `ConversationSelector.list_for_user` exactly."""

    status: str | None
    page: int
    page_size: int


def parse_conversation_list_params(query_params) -> ConversationListParams:
    page, page_size = _parse_pagination(query_params)
    status = query_params.get("filter[status]")
    if status and status not in ConversationStatus.values():
        raise ValidationFailed(f"'{status}' is not a valid status filter.", details={"fields": [{"field": "filter[status]", "code": "INVALID_CHOICE"}]})
    return ConversationListParams(status=status, page=page, page_size=page_size)


def parse_pagination_only(query_params) -> tuple[int, int]:
    """Used by the message-list endpoint, which has no filter beyond pagination."""
    return _parse_pagination(query_params)
