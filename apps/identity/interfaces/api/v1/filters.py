"""
Admin user-list filter parsing.

Matches Enterprise REST API Blueprint §10's uniform `filter[field]=value`
query-parameter shape. Kept as a plain parsing function rather than a
django-filter FilterSet, since `AdminListUsers` (application/services/
staff.py) takes plain keyword arguments, not a queryset -- this
function's only job is translating `request.query_params` into that
call's arguments, with no query-building logic of its own (that stays
inside the repository, per Django Implementation Blueprint §3).
"""
from __future__ import annotations

from dataclasses import dataclass

from apps.identity.domain.enums import LanguagePreference, UserStatus

ALLOWED_SORT_FIELDS = {"created_at", "-created_at", "full_name", "-full_name", "last_activity", "-last_activity"}


@dataclass(frozen=True, slots=True)
class AdminUserListParams:
    status: str | None
    language: str | None
    role: str | None
    query: str | None
    ordering: str
    page: int
    page_size: int


def parse_admin_user_list_params(query_params) -> AdminUserListParams:
    from common.exceptions import ValidationFailed

    status = query_params.get("filter[status]")
    if status and status not in UserStatus.values():
        raise ValidationFailed(f"'{status}' is not a valid status filter.", details={"fields": [{"field": "filter[status]", "code": "INVALID_CHOICE"}]})

    language = query_params.get("filter[language]")
    if language and language not in LanguagePreference.values():
        raise ValidationFailed(f"'{language}' is not a valid language filter.", details={"fields": [{"field": "filter[language]", "code": "INVALID_CHOICE"}]})

    ordering = query_params.get("sort", "-created_at")
    if ordering not in ALLOWED_SORT_FIELDS:
        raise ValidationFailed(
            f"'{ordering}' is not a sortable field. Allowed: {sorted(ALLOWED_SORT_FIELDS)}",
            details={"fields": [{"field": "sort", "code": "INVALID_CHOICE"}]},
        )

    try:
        page = max(int(query_params.get("page", 1)), 1)
        page_size = min(max(int(query_params.get("page_size", 20)), 1), 100)
    except ValueError as exc:
        raise ValidationFailed("page/page_size must be integers.") from exc

    return AdminUserListParams(
        status=status,
        language=language,
        role=query_params.get("filter[role]"),
        query=query_params.get("q"),
        ordering=ordering,
        page=page,
        page_size=page_size,
    )
