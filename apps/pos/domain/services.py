"""
POS domain services.

**Zero Domain Services exist this phase -- a deliberate, reasoned
conclusion, not an oversight.** `Sale` is the only aggregate in this
Domain; there is no second aggregate for a cross-aggregate rule to
coordinate between, unlike Analytics (`MetricDefinition`+
`AnalyticsSnapshot`) or Notifications (`Notification`+
`NotificationPreference`). Every rule considered during design
belongs naturally on `Sale` itself:

- A hypothetical `SaleTotalCalculationPolicy` -- rejected as
  redundant: `Sale.total()` (see aggregates.py) already computes this
  directly by summing each line item's own `line_total()`, using the
  Shared Kernel `Money`'s own arithmetic; a wrapping service would add
  nothing.
- A hypothetical `ProductAvailabilityPolicy` (checking Inventory
  before allowing a line item) -- rejected: this would require POS to
  reach into Inventory's own domain, a forward dependency this task's
  own Section 5 explicitly forbids without an evidenced Port: no such
  Port exists yet, so this check is deferred, not fabricated.

If a genuine second aggregate or cross-aggregate rule is certified in
a future phase, add a service here then -- not preemptively now.
"""
from __future__ import annotations
