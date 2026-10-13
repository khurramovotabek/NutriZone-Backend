"""
Admin application services: AdminListUsers, AdminGetUser,
AdminUpdateUserStatus. Backs `/api/v1/admin/users*` (Enterprise REST
API Blueprint §13.1).
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.identity.application.ports import UserRepository
from apps.identity.application.services.profile import _invalidate_profile_cache
from apps.identity.domain.events import UserBlocked
from common.exceptions import ResourceNotFound
from core.audit import AuditEventBuilder


class AdminListUsers:
    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    def execute(self, status: str | None, query: str | None, page: int, page_size: int):
        return self._user_repo.list_for_admin(status=status, query=query, page=page, page_size=page_size)


class AdminGetUser:
    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    def execute(self, user_id: uuid.UUID):
        user = self._user_repo.get_by_id(user_id)
        if user is None:
            raise ResourceNotFound("User not found.")
        return user


class AdminUpdateUserStatus:
    def __init__(self, user_repo: UserRepository, stage_events) -> None:
        self._user_repo = user_repo
        self._stage_events = stage_events

    @transaction.atomic
    def execute(self, actor_user_id: uuid.UUID, target_user_id: uuid.UUID, new_status: str, reason: str | None = None):
        user = self._user_repo.get_by_id(target_user_id)
        if user is None:
            raise ResourceNotFound("User not found.")

        previous_status = user.status.value

        if new_status == "blocked":
            event = user.block(reason=reason)
            self._stage_events([("UserBlocked", event.to_payload())])
        elif new_status == "active":
            user.activate()
        else:
            from common.exceptions import ValidationFailed

            raise ValidationFailed(
                f"'{new_status}' is not a valid target status.",
                details={"fields": [{"field": "status", "code": "INVALID_CHOICE"}]},
            )

        saved = self._user_repo.save(user)
        _invalidate_profile_cache(target_user_id)

        audit = AuditEventBuilder(context_schema="identity", actor_id=str(actor_user_id))
        audit.updated(
            entity_type="User",
            entity_id=str(target_user_id),
            before={"status": previous_status},
            after={"status": new_status},
        )
        return saved
