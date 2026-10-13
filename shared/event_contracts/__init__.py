"""
Typed event payload contracts.

Each business module registers its emitted events' payload shapes here
(as dataclasses) when it is implemented, and calls
`core.events.registry.registry.register(...)` at Django app-ready time
so the Domain Event Catalogue (Domain Architecture Specification §6) is
enforced at runtime, not just documented.

Empty at foundation stage -- no business events exist yet. See
core/events/registry.py for the registration mechanism and
core/outbox/publisher.py for how a module stages an event payload that
conforms to a contract registered here.
"""
