"""
Django signal receivers -- Infrastructure signals only, matching the
identical, already-established rationale in `apps.geo`/`apps.store`/
`apps.inventory.infrastructure.signals`.

No actual Django model signal is needed: `common/models/base.py`'s
save() override already handles `updated_at`/`version` maintenance,
and every cache/audit/metrics side effect is driven by the Outbox
relay (`tasks.py::relay_outbox_events` -> `event_handlers.py::
handle_pricing_event`), not a signal -- a signal would fire
synchronously inside the mutating transaction, defeating the Outbox
pattern's purpose.
"""
