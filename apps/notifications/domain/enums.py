"""
Notifications domain enums.

`notifications` is Domain Architecture Specification §2.13, confirmed
by reading the module's own placeholder scaffold before any code was
written (its README cited that section explicitly; no literal
specification document exists anywhere in this repository to
cross-check against -- consistent with every prior module in this
build, not a new discrepancy).

**A deliberate genericness, disclosed rather than assumed**:
`NotificationType` is intentionally broad (TRANSACTIONAL/PROMOTIONAL/
SYSTEM), not a per-source-module taxonomy (e.g. ORDER_SHIPPED,
CHAT_MESSAGE_RECEIVED). Notifications' own Domain has no business
knowing the internal event catalogue of every other bounded context
-- Chat's own `NotificationGateway.notify_chat_event()` placeholder
(confirmed during Step 1) already establishes that other modules
trigger notifications generically, not by having Notifications import
their own Domain concepts.
"""
from __future__ import annotations

from common.utils import DomainStrEnum


class NotificationType(DomainStrEnum):
    TRANSACTIONAL = "transactional"
    PROMOTIONAL = "promotional"
    SYSTEM = "system"


class NotificationPriority(DomainStrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationChannel(DomainStrEnum):
    """TELEGRAM is included on real evidence, not speculation -- `apps.identity.domain.aggregates.User.telegram_username` genuinely exists as captured contact data, confirmed during this phase's own Step 1."""

    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"
    IN_APP = "in_app"
    TELEGRAM = "telegram"


class NotificationStatus(DomainStrEnum):
    """The recipient-facing lifecycle -- distinct from `DeliveryStatus`, which tracks each individual channel attempt. CANCELLED is terminal, matching the pattern already established by Chat's own ARCHIVED status."""

    UNSEEN = "unseen"
    SEEN = "seen"
    READ = "read"
    CANCELLED = "cancelled"


class DeliveryStatus(DomainStrEnum):
    """Per-channel delivery-attempt lifecycle, owned by `NotificationDelivery` -- see entities.py."""

    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
