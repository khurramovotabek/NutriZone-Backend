"""
Platform API permission classes.

Reuses Identity's RBAC engine exactly, matching every prior module's
`interfaces/api/v1/permissions.py` pattern. `GET /settings/feature-flags`
itself uses DRF's own `AllowAny` directly in views.py (matching REST
API Blueprint §13.18's "authenticated or anonymous" requirement, and
Products' own public search endpoint's identical precedent) -- no
custom permission class is needed for that one endpoint.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from common.permissions import HasPermissionCode


class BasePlatformPermission(BasePermission):
    """Base class -- subclasses set `permission_code`. Fails closed if no code is set."""

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


class ManageFeatureFlags(BasePlatformPermission):
    """Matches Domain Architecture Specification §2.18's own explicit call-out: "highest-blast-radius permission in the system -- restrict tightly"."""

    permission_code = "platform.flag.manage"
