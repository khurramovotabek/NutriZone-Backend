"""
Django signal receivers -- Infrastructure signals only, matching the
identical, already-established rationale in every prior module's
`infrastructure/signals.py`.

No actual Django model signal is needed: `common/models/base.py`'s
save() override already handles `updated_at`/`version` maintenance,
and every cache/audit/metrics side effect is driven by the Outbox
relay (`tasks.py::relay_outbox_events` -> `event_handlers.py::
handle_ordering_event`), not a signal.
"""
