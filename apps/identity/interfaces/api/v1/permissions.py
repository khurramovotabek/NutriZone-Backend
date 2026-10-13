"""
Identity-specific permission classes.

`common.permissions.HasPermissionCode` reads `required_permission_code`
off the *view* it's attached to (not off the permission class itself),
per its own docstring's usage example -- so views declare the
permission code directly (see views.py's `required_permission_code`
class attributes) and use `HasPermissionCode` unmodified. This module
only adds the one Identity-specific permission shape
(`HasPermissionCode` doesn't cover) -- the self-service "must be
authenticated, no specific permission code required" case.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission


class IsAuthenticatedIdentityUser(BasePermission):
    """Baseline check for any self-service endpoint (`/identity/users/me`, sessions) -- just requires a valid, non-blocked token."""

    def has_permission(self, request, view) -> bool:
        return bool(request.user and getattr(request.user, "is_authenticated", False))
