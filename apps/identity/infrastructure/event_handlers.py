"""
Consumed-event handlers.

Per Domain Architecture Specification §2.1's Communication Matrix,
`identity` is a foundational/upstream context: "Domain Events
(Consumed): None -- Identity is a core/upstream context and must not
depend on downstream event data to make identity decisions." This file
is therefore intentionally empty, and MUST remain so -- if a future
change seems to require identity to consume another module's event,
that is a signal to revisit the Domain Architecture Specification's
Communication Matrix (§4 there) before adding a handler here, not a
reason to add one directly (MIC §7's "Consumed Events" rule).
"""
