"""
Django signal receivers -- Infrastructure signals only, matching the
identical, already-established rationale in every prior module's
`infrastructure/signals.py`. Intentionally empty: every cache/audit/
metrics side effect is driven by the Outbox relay (`tasks.py::
relay_outbox_events` -> `event_handlers.py::handle_review_event`),
not a signal -- a signal would fire synchronously inside the mutating
transaction, defeating the Outbox pattern's purpose.
"""
