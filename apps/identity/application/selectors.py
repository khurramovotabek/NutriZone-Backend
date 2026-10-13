"""
Identity read-side selectors -- for queries that don't map to a single
"use case" the way application/services/ methods do (Django
Implementation Blueprint §3). Kept thin at this stage: the admin
list/detail reads are already covered by AdminListUsers/AdminGetUser
in application/services/staff.py since they map 1:1 to a single REST
endpoint each; this module exists for the future case of a read that
composes data no single service owns (e.g. a combined "user + their
role names + their session count" projection for an Admin CRM detail
screen), added when that concrete need arises rather than speculatively
now.
"""
from __future__ import annotations

import uuid

from apps.identity.application.ports import RoleAssignmentRepository, UserRepository


class GetUserWithRoles:
    """Composes a User with its assigned role codes -- the shape the Admin CRM's user detail screen needs."""

    def __init__(self, user_repo: UserRepository, assignment_repo: RoleAssignmentRepository) -> None:
        self._user_repo = user_repo
        self._assignment_repo = assignment_repo

    def execute(self, user_id: uuid.UUID) -> dict:
        from common.exceptions import ResourceNotFound

        user = self._user_repo.get_by_id(user_id)
        if user is None:
            raise ResourceNotFound("User not found.")
        role_codes = self._assignment_repo.list_role_codes_for_user(user_id)
        return {"user": user, "role_codes": role_codes}
