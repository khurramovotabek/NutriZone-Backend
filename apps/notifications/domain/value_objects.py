"""
Notifications domain value objects.

**A deliberate, disclosed departure from this phase's own suggested
concepts list**: no `RecipientReference`/`ExternalReference`/
`TemplateKey`/`DeliveryAttemptCount`/`ScheduledAt` value objects are
defined.

- `Notification.recipient_id` is a plain `uuid.UUID`, matching the
  established convention confirmed in Step 1 (Identity's `User.id`)
  and used by every prior module for cross-context references.
- `template_key`, where recorded at all, is a plain optional `str`
  field on `Notification` -- no repository evidence establishes an
  actual template-key format/validation convention, so fabricating
  one here would be inventing a rule Domain has no business owning.
- No `ExternalReference` VO exists on `NotificationDelivery` --
  provider-assigned identifiers are an opaque, unvalidated fact
  Domain merely records (a plain optional `str`), not something
  Domain interprets or constrains.
- `DeliveryAttemptCount`/retry semantics are explicitly out of
  Domain's scope per this phase's own instruction ("retry semantics"
  belongs to Application/Infrastructure) -- no such VO exists.
- `ScheduledAt` does not exist -- scheduling is explicitly deferred
  to Application/Infrastructure per this phase's own instruction (H:
  "scheduling... may belong primarily to Application/Infrastructure").
"""
from __future__ import annotations

from dataclasses import dataclass

from apps.notifications.domain.exceptions import EmptyNotificationContent, NotificationContentTooLong

MAX_TITLE_LENGTH = 150
MAX_BODY_LENGTH = 1000


@dataclass(frozen=True, slots=True)
class NotificationTitle:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise EmptyNotificationContent("NotificationTitle must not be empty or whitespace-only.", details={"fields": [{"field": "title", "code": "EMPTY"}]})
        if len(self.value) > MAX_TITLE_LENGTH:
            raise NotificationContentTooLong(f"NotificationTitle must not exceed {MAX_TITLE_LENGTH} characters (got {len(self.value)}).", details={"fields": [{"field": "title", "code": "TOO_LONG"}]})


@dataclass(frozen=True, slots=True)
class NotificationBody:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise EmptyNotificationContent("NotificationBody must not be empty or whitespace-only.", details={"fields": [{"field": "body", "code": "EMPTY"}]})
        if len(self.value) > MAX_BODY_LENGTH:
            raise NotificationContentTooLong(f"NotificationBody must not exceed {MAX_BODY_LENGTH} characters (got {len(self.value)}).", details={"fields": [{"field": "body", "code": "TOO_LONG"}]})
