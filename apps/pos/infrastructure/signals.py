"""
Django signal receivers -- Infrastructure signals only, matching the
identical, already-established rationale in every prior module's
`infrastructure/signals.py`. Intentionally empty: every metrics side
effect is driven by the Outbox relay (`tasks.py::relay_outbox_events`
-> `event_handlers.py::handle_pos_event`), not a signal.
"""
