"""
Notifications domain exceptions.

**A deliberate reordering from this phase's own suggested file
order**: this file is written immediately after `value_objects.py`,
not after `entities.py`, because `value_objects.py` deliberately
imports its specific exceptions directly (`EmptyNotificationContent`,
`NotificationContentTooLong`) from the start -- applying the lesson
already learned the hard way in Reviews' and Chat's own Phase 1
(where generic `ValidationFailed` was initially left in place and had
to be fixed retroactively after certification found the specific
exceptions were dead code). Getting the dependency order right
proactively here avoids repeating that exact mistake a third time.
"""
from __future__ import annotations

from common.exceptions import BusinessRuleViolation, ConflictError, ValidationFailed


class InvalidNotificationTransition(ConflictError):
    """The general fallback for any wrong-state Notification transition (e.g. cancelling an already-READ notification)."""

    code = "INVALID_NOTIFICATION_TRANSITION"


class NotificationAlreadyCancelled(ConflictError):
    code = "NOTIFICATION_ALREADY_CANCELLED"


class NotificationAlreadyDelivered(BusinessRuleViolation):
    """Raised when cancellation is attempted after at least one channel has already confirmed DELIVERED -- a cross-check against delivery state, distinct from the notification's own status transition rules."""

    code = "NOTIFICATION_ALREADY_DELIVERED"


class DeliveryNotFound(ValidationFailed):
    code = "DELIVERY_NOT_FOUND"


class InvalidDeliveryTransition(ConflictError):
    """The general fallback for wrong-state NotificationDelivery transitions (e.g. confirming a delivery that already FAILED)."""

    code = "INVALID_DELIVERY_TRANSITION"


class EmptyNotificationContent(ValidationFailed):
    """Shared by both `NotificationTitle` and `NotificationBody` -- both fields fail the identical "empty" case, and a single specific exception type serves both without duplicating a near-identical class."""

    code = "EMPTY_NOTIFICATION_CONTENT"


class NotificationContentTooLong(ValidationFailed):
    """Shared by both `NotificationTitle` and `NotificationBody`, matching `EmptyNotificationContent`'s own rationale."""

    code = "NOTIFICATION_CONTENT_TOO_LONG"
