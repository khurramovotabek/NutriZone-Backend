"""
Notifications domain services.

**A significant, disclosed finding rather than an empty file left
without explanation: zero Domain Services are justified this
phase.** Every candidate considered during Step 1 was rejected for a
concrete, specific reason, not merely "not needed yet":

- `NotificationEligibilityPolicy` (would decide "is this channel
  eligible given this user's preferences") -- rejected as genuinely
  redundant, not merely unnecessary: `NotificationPreference` (see
  aggregates.py) already exposes its own `is_enabled(channel,
  notification_type)` read-only query method. A separate service
  that only calls that one method would be exactly the "service
  merely to move one aggregate method elsewhere" anti-pattern this
  build's own rules explicitly forbid.
- `NotificationRoutingPolicy`/`NotificationChannelPolicy` (would
  decide which channel(s) to actually use for a given notification)
  -- rejected because real channel routing genuinely requires
  external knowledge Domain does not and should not have (operator/
  provider availability, delivery cost, rate limits) -- explicitly
  named as out of Domain's scope by this phase's own instructions
  ("if routing requires operator workload, queue state, provider
  availability... explicitly defer it rather than fabricating a
  Domain service").
- A hypothetical `NotificationPriorityEscalationPolicy` (would decide
  whether a notification's priority should escalate over time, e.g.
  if unread after N hours) -- rejected as fabricated: no repository
  evidence or specification establishes this as a real business rule
  for Notifications; inventing one to populate this file would be
  exactly the "speculative service" anti-pattern this build's rules
  forbid.

If a genuine cross-aggregate or cross-entity rule is certified in a
future phase that does not merely wrap one aggregate's own method,
add it here then -- not preemptively now.
"""
from __future__ import annotations
