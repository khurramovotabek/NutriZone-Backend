"""
Notifications API permission classes.

Reuses Identity's RBAC engine exactly, matching every prior module's
`interfaces/api/v1/permissions.py` pattern. Fails closed by default.

**A disclosed authorization boundary note, matching Chat's own
precedent**: no permission class here checks object-level ownership
directly (e.g. "is this notification actually addressed to this
user") -- DRF's permission-class hook runs before the resource is
resolved. That check happens inside each view itself, against the
real loaded aggregate/row, not duplicated here as a second, parallel
mechanism that could silently drift out of sync.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from common.permissions import HasPermissionCode


class BaseNotificationPermission(BasePermission):
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


class ViewOwnNotifications(BaseNotificationPermission):
    permission_code = "notifications.notification.view_own"


class ManageOwnNotifications(BaseNotificationPermission):
    """Covers mark_seen/mark_read/cancel -- the user-controlled lifecycle actions on their own notification."""

    permission_code = "notifications.notification.manage_own"


class ManageOwnPreferences(BaseNotificationPermission):
    permission_code = "notifications.preference.manage_own"


class CreateNotification(BaseNotificationPermission):
    """System/admin-initiated -- creating a notification is not typically a self-service end-user action, matching the certified Domain's own likely-system-triggered `Notification.create()` factory."""

    permission_code = "notifications.notification.create"
