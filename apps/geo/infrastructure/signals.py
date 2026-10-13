"""
Django signal receivers -- framework-level housekeeping ONLY, per the
explicit, repeated prohibition in Django Implementation Blueprint
§4/§16 and MIC §4/§9 (restated here, per the identical rationale
`apps/identity/infrastructure/signals.py` and
`apps/products/infrastructure/signals.py` already document).

No housekeeping signal is currently needed: `common/models/base.py`'s
save() override already handles `updated_at`/`version` maintenance
without a signal. Kept as an explicit, empty, documented placeholder
per MIC §2.1's mandatory folder structure -- this module's brief's
"Cache invalidation / Search indexing / Metrics / Audit hooks" signal
examples are all already handled by `event_handlers.py::handle_geo_event`
(driven by the Outbox relay, not a Django signal) -- routing them
through a Django signal instead would mean they fire synchronously
inside the same request/transaction as the mutation, which is exactly
what the Outbox pattern exists to avoid (Domain Architecture
Specification §6).
"""
