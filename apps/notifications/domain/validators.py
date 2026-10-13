"""
Notifications domain validators -- thin, intention-revealing wrappers
over value object constructors, matching every prior module's
domain/validators.py pattern.
"""
from __future__ import annotations

from apps.notifications.domain.value_objects import NotificationBody, NotificationTitle


def NotificationTitleValidator(value: str) -> NotificationTitle:  # noqa: N802
    return NotificationTitle(value)


def NotificationBodyValidator(value: str) -> NotificationBody:  # noqa: N802
    return NotificationBody(value)
