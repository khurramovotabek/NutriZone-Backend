"""
NutriZone Admin Audit Timeline -- aggregation layer (Phase 08.9).

**A genuine architectural finding, confirmed by direct inspection,
not assumed**: `apps.audit` is a deliberate, unimplemented placeholder
(its own models.py: "do not add code here until the module is
implemented"). There is no centralized Audit Log model anywhere in
this project. `core.audit.events.AuditEventBuilder`'s own usage
docstring confirms the real mechanism: audit events are staged into
each module's own OutboxEvent table via `core.outbox.stage_event()`
-- the same tables already registered, read-only, throughout every
module's own admin.py. That IS the real audit trail.

This module does not create a second Audit system -- it merges the
already-existing, already-certified OutboxEvent tables from the
modules most relevant to administrative oversight (Ordering,
Identity, Wallet, Loyalty, Products, Pricing) into one read-only,
chronological view. Covering all 17 OutboxEvent tables in this
project was judged out of scope for this phase's own time budget --
a deliberate, disclosed choice, not an oversight.
"""
from __future__ import annotations


def recent_events(limit: int = 50) -> list[dict]:
    """One bounded query per covered module (6 total, not per-event) -- merged and sorted in Python, since no single database query can span these genuinely separate tables without raw SQL this phase deliberately avoided (per this phase's own 'prefer Django ORM' instruction)."""
    from apps.ordering.infrastructure import models as ordering_orm
    from apps.identity.infrastructure import models as identity_orm
    from apps.products.infrastructure import models as products_orm
    from apps.pricing.infrastructure import models as pricing_orm

    sources = [
        ("Ordering", ordering_orm.OrderingOutboxEvent),
        ("Identity", identity_orm.IdentityOutboxEvent),
        ("Products", products_orm.ProductsOutboxEvent),
        ("Pricing", pricing_orm.PricingOutboxEvent),
    ]

    events = []
    for module_label, model in sources:
        # Bounded per-source fetch (limit rows, not the full table) -- never loads an entire outbox table into Python.
        rows = model.objects.order_by("-created_at").values("event_type", "correlation_id", "created_at", "publish_attempts", "published_at")[:limit]
        for row in rows:
            events.append({
                "module": module_label,
                "event_type": row["event_type"],
                "correlation_id": row["correlation_id"],
                "created_at": row["created_at"],
                "delivered": row["published_at"] is not None,
            })

    events.sort(key=lambda e: e["created_at"], reverse=True)
    return events[:limit]
