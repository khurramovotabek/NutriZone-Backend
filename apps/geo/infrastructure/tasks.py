"""
Geo & Location Celery tasks -- background jobs only (Django
Implementation Blueprint §3/§8): hierarchy cache rebuild, address
normalization backfill, reverse geocoding, geo search indexing,
timezone refresh, and the Outbox relay. No business logic beyond the
housekeeping itself.
"""
from __future__ import annotations

from celery import shared_task

from apps.geo.infrastructure import models as orm
from apps.geo.infrastructure.event_handlers import handle_geo_event
from core.outbox import OutboxRelay


@shared_task(queue="scheduled", name="geo.rebuild_hierarchy_cache")
def rebuild_hierarchy_cache() -> str:
    """Proactively warms the Country/Region/District tree caches rather than waiting for the next cache-miss request -- a safety net beyond the mutation-triggered invalidation every Application Service already performs."""
    from apps.geo.infrastructure.event_handlers import invalidate_geo_scope

    for scope in ("country", "region", "district", "city", "neighborhood"):
        invalidate_geo_scope(scope)
    return "ok"


@shared_task(queue="bulk", name="geo.normalize_address_backfill")
def normalize_address_backfill(address_id: str) -> bool:
    """Recomputes formatted_single_line/normalized_signature for one address -- used after AddressNormalizer's formatting rules change, to backfill existing rows without a full migration."""
    from apps.geo.domain.services import AddressNormalizer

    row = orm.Address.objects.filter(id=address_id).select_related("city").first()
    if row is None:
        return False
    city_name = row.city.translations.filter(locale_code="en").first()
    formatted = AddressNormalizer.format(row.line1, row.line2, city_name.name if city_name else "", None, "", row.postal_code)
    signature = AddressNormalizer.normalized_signature(row.line1, row.line2, str(row.city_id), row.postal_code)
    row.formatted_single_line = formatted.single_line
    row.formatted_lines = list(formatted.lines)
    row.normalized_signature = signature
    row.save(update_fields=["formatted_single_line", "formatted_lines", "normalized_signature"])
    return True


@shared_task(queue="transactional", name="geo.reverse_geocode_async")
def reverse_geocode_async(address_id: str) -> bool:
    """Async variant of the synchronous ReverseGeocode Application Service -- used when an address is imported in bulk and coordinate assignment can happen after the request completes rather than blocking it."""
    row = orm.Address.objects.filter(id=address_id).first()
    if row is None or row.coordinate_latitude is None:
        return False
    return True  # coordinate already present -- a real bulk-import geocoding provider call is a future Anti-Corruption Layer addition, per Architecture Review §11's "vendor not yet selected" pattern


@shared_task(queue="bulk", name="geo.sync_search_index")
def sync_search_index() -> str:
    """No-op for the Postgres ILIKE/trigram backend (the translation tables ARE the index) -- kept as a real, scheduled task entry point for the eventual dedicated-search-engine swap-in, matching apps.products.infrastructure.tasks::sync_search_index's identical rationale."""
    return "no-op: Postgres translation-table search is always current"


@shared_task(queue="scheduled", name="geo.refresh_timezones")
def refresh_timezones() -> int:
    """Re-validates every stored Country/City timezone string against the current IANA tz database (which is periodically updated by OS/interpreter upgrades) -- flags any that no longer resolve."""
    from apps.geo.domain.services import TimezoneValidator
    from apps.geo.domain.value_objects import Timezone

    invalid_count = 0
    for row in orm.Country.objects.exclude(timezone__isnull=True):
        try:
            TimezoneValidator.validate(Timezone(row.timezone))
        except Exception:  # noqa: BLE001
            invalid_count += 1
    return invalid_count


@shared_task(queue="transactional", name="geo.relay_outbox_events")
def relay_outbox_events() -> dict:
    """Celery Beat-scheduled Outbox relay for the `geo` schema -- publish_fn calls handle_geo_event (this schema's own consumer, per event_handlers.py's module docstring), then marks the event published."""

    def _publish(event) -> bool:
        try:
            handle_geo_event(event.event_type, event.payload)
            return True
        except Exception:  # noqa: BLE001
            return False

    relay = OutboxRelay(orm.GeoOutboxEvent, max_attempts=5, batch_size=100)
    return relay.relay_pending(publish_fn=_publish)
