"""
Geo & Location API permission classes.

Reuses Identity's RBAC engine exactly, matching
`apps.products.interfaces.api.v1.permissions`'s exact pattern -- every
class below is a thin, named wrapper calling `common.permissions.
HasPermissionCode.resolver` (wired once, globally, by
`apps.identity.apps.IdentityConfig.ready()`) with a Geo-specific
permission code.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission


class _GeoPermission(BasePermission):
    """Base class -- subclasses set `permission_code`."""

    permission_code: str = ""

    def has_permission(self, request, view) -> bool:
        if not self.permission_code:
            return False  # fail closed
        if not request.user or not getattr(request.user, "is_authenticated", False):
            return False

        from common.permissions import HasPermissionCode

        resolver = HasPermissionCode.resolver
        if resolver is None:
            return False

        store_id = getattr(view, "get_permission_store_id", lambda: None)()
        return resolver.user_has_permission(request.user.id, self.permission_code, store_id)


class GeoViewPermission(_GeoPermission):
    """Staff read access to admin hierarchy endpoints."""

    permission_code = "geo.hierarchy.view"


class GeoManagePermission(_GeoPermission):
    """Create/update/delete Country/Region/District/City/Neighborhood."""

    permission_code = "geo.hierarchy.manage"


class GeoAddressPermission(_GeoPermission):
    """Manage any address (staff override) -- self-service address management for the owning user is handled by AddressOwnerPermission, below."""

    permission_code = "geo.address.manage_any"


class AddressOwnerPermission(BasePermission):
    """Object-level: a user may manage their own address (owner_type='user', owner_id=request.user.id) without any special permission code -- everyone can manage their own addresses by default, matching the platform-wide self-service pattern already established by Identity's session management."""

    def has_permission(self, request, view) -> bool:
        return bool(request.user and getattr(request.user, "is_authenticated", False))

    def has_object_permission(self, request, view, obj) -> bool:
        return obj.owner_type == "user" and obj.owner_id == getattr(request.user, "id", None)
