"""
Consumed-event handlers.

Per Domain Architecture Specification §2.2's Communication Matrix,
`catalog` (Products) is upstream/foundational relative to Pricing,
Inventory, Ordering, Search, and Reviews -- it is *read* by ID
reference from those contexts, never a subscriber to their events.
This file is therefore intentionally empty, matching
`apps/identity/infrastructure/event_handlers.py`'s identical rationale
and MUST remain so unless the Domain Architecture Specification's
Communication Matrix is itself amended first (MIC §7's "Consumed
Events" rule).
"""
