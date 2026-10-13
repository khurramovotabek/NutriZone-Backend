"""
Notifications OpenAPI tag registration.

Two tags, matching the "X / X Admin" convention already used by
Loyalty/Reviews/Chat. `Notifications Admin` covers only the single
system/admin-initiated `create` endpoint -- every other capability is
user-self-service, tagged plainly `Notifications`.
"""
from __future__ import annotations

NOTIFICATIONS_TAG = "Notifications"
NOTIFICATIONS_ADMIN_TAG = "Notifications Admin"

ALL_NOTIFICATIONS_TAGS = (NOTIFICATIONS_TAG, NOTIFICATIONS_ADMIN_TAG)
