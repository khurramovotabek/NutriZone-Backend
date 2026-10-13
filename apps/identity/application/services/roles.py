"""
RBAC application services: AssignRole, RemoveRole, SetRolePermissions, CheckPermission.

`CheckPermission` is the concrete `PermissionResolver` implementation
that `common/permissions/permissions.py::HasPermissionCode.resolver`
is wired to (Enterprise REST API Blueprint §5) -- every other module's
API layer ultimately calls this class to answer "may this user perform
this action."
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.identity.application.ports import PermissionRepository, RoleAssignmentRepository, RoleRepository
from apps.identity.domain.exceptions import RoleAlreadyAssignedError
from common.exceptions import ResourceNotFound
from core.caching import TTL_SHORT, cache_key, get_redis_client


class AssignRole:
    def __init__(self, role_repo: RoleRepository, assignment_repo: RoleAssignmentRepository, stage_events) -> None:
        self._role_repo = role_repo
        self._assignment_repo = assignment_repo
        self._stage_events = stage_events

    @transaction.atomic
    def execute(self, user_id: uuid.UUID, role_code: str, store_id: uuid.UUID | None = None):
        role = self._role_repo.get_by_code(role_code)
        if role is None:
            raise ResourceNotFound(f"Role '{role_code}' does not exist.")

        if self._assignment_repo.exists(user_id, role.id, store_id):
            raise RoleAlreadyAssignedError("This role is already assigned to this user (with this store scope).")

        event = role.assign_to(user_id, store_id)
        from apps.identity.domain.entities import RoleAssignment

        assignment = RoleAssignment(id=uuid.uuid4(), user_id=user_id, role_id=role.id, store_id=store_id)
        saved = self._assignment_repo.assign(assignment)
        self._stage_events([("UserRoleAssigned", event.to_payload())])
        _invalidate_permission_cache(user_id)
        return saved


class RemoveRole:
    """Takes one role assignment away from a user (dashboard → Foydalanuvchi rollari / the user's card)."""

    def __init__(self, assignment_repo: RoleAssignmentRepository) -> None:
        self._assignment_repo = assignment_repo

    @transaction.atomic
    def execute(self, assignment_id: uuid.UUID, actor_id=None) -> None:
        removed = self._assignment_repo.remove(assignment_id)
        if removed is None:
            raise ResourceNotFound("Role assignment not found.")
        _invalidate_permission_cache(removed["user_id"])
        from core.audit import AuditEventBuilder

        AuditEventBuilder(context_schema="identity", actor_id=str(actor_id)).deleted(
            entity_type="UserRole", entity_id=str(assignment_id), before={k: str(v) if v else None for k, v in removed.items()},
        )


class SetRolePermissions:
    """
    Replaces a role's permission set with exactly `permission_codes` (the dashboard's role editor). Unknown codes are
    rejected; returns (added, removed) codes. Users holding the role pick the change up within the permission
    cache's short TTL (see CheckPermission).
    """

    def __init__(self, role_repo: RoleRepository, permission_repo: PermissionRepository) -> None:
        self._role_repo = role_repo
        self._permission_repo = permission_repo

    @transaction.atomic
    def execute(self, role_id: uuid.UUID, permission_codes, actor_id=None) -> tuple[list[str], list[str]]:
        role = self._role_repo.get_by_id(role_id)
        if role is None:
            raise ResourceNotFound("Role not found.")
        wanted = set(permission_codes or [])
        before = set(self._permission_repo.list_permission_codes_for_role(role_id))
        added, removed = self._permission_repo.set_permissions_for_role(role_id, wanted)
        if added or removed:
            from core.audit import AuditEventBuilder

            AuditEventBuilder(context_schema="identity", actor_id=str(actor_id)).updated(
                entity_type="Role", entity_id=str(role_id), before={"permissions": sorted(before)}, after={"permissions": sorted(wanted)},
            )
        return added, removed


class CheckPermission:
    """
    The single, canonical `user_has_permission()` implementation --
    wired into `common.permissions.HasPermissionCode.resolver` at
    Django startup (see apps/identity/apps.py). Short-TTL Redis-cached
    per (user, permission_code, store_id) tuple, since this is called
    on effectively every authenticated API request platform-wide.
    """

    def __init__(self, assignment_repo: RoleAssignmentRepository) -> None:
        self._assignment_repo = assignment_repo

    def user_has_permission(self, user_id: uuid.UUID, permission_code: str, store_id: uuid.UUID | None = None) -> bool:
        cache_k = cache_key(user_id, permission_code, store_id or "-", namespace="identity:permissions")
        client = get_redis_client()
        cached = client.get(cache_k)
        if cached is not None:
            return cached == "1"

        effective_codes = self._assignment_repo.list_effective_permission_codes(user_id, store_id)
        result = permission_code in effective_codes
        client.set(cache_k, "1" if result else "0", ex=TTL_SHORT)
        return result


def _invalidate_permission_cache(user_id: uuid.UUID) -> None:
    """
    Called after any role/permission change for a user. A full key
    scan-and-delete is avoided by relying on the short TTL above to
    self-heal within TTL_SHORT seconds -- acceptable staleness window
    per Enterprise Database Blueprint §8's caching-vs-correctness
    tradeoff philosophy, given permission changes are rare relative to
    permission checks.
    """
