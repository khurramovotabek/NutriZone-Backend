"""
Django signal receivers -- Infrastructure signals only, per this
phase's explicit "register Infrastructure signals only / no business
logic / no ORM mutations / only delegate to handlers" instruction.
Matches the identical, already-established rationale in
`apps.geo.infrastructure.signals`/`apps.store.infrastructure.signals`.

No actual Django model signal (post_save, pre_delete, etc.) is needed:
`common/models/base.py`'s save() override already handles
`updated_at`/`version` maintenance without one, and every side effect
this phase's brief describes (cache invalidation, Outbox publish,
audit, metrics) is driven by the Outbox relay
(`tasks.py::relay_outbox_events` -> `event_handlers.py::
handle_inventory_event`), which "delegates to handlers" exactly as
required -- a Django signal would fire synchronously inside the
mutating request's own transaction, defeating the Outbox pattern's
purpose.
"""
