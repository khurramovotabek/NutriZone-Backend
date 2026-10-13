"""
Audit API permission classes. REST API Blueprint §13's own text for
`GET /internal/audit/activity` allows either `identity.user.view` or
"a dedicated `audit.log.view`" -- this module defines its own code,
matching the established repository-wide convention that every module
owns its own permission namespace (`platform.flag.manage`,
`pos.sale.manage`, etc.), rather than reaching into Identity's.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from common.permissions import HasPermissionCode


class BaseAuditPermission(BasePermission):
    permission_code: str = ""

    def has_permission(self, request, view) -> bool:
        if not self.permission_code:
            return False  # fail closed
        if not request.user or not getattr(request.user, "is_authenticated", False):
            return False
        resolver = HasPermissionCode.resolver
        if resolver is None:
            return False
        store_id = getattr(view, "get_permission_store_id", lambda: None)()
        return resolver.user_has_permission(request.user.id, self.permission_code, store_id)


class ViewActivityTimeline(BaseAuditPermission):
    permission_code = "audit.log.view"
