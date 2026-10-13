"""
Consumed-event handlers for Geo & Location, plus the cache
invalidation helper functions they (and the composition root's query
wiring) use.

Scope note: unlike `apps.identity`/`apps.products` (both upstream-only
in the Communication Matrix sense), this phase's brief explicitly asks
Geo to register handlers for its OWN emitted events (CountryCreated,
RegionCreated, ..., AddressUpdated) -- i.e. Geo consumes its own
Outbox stream to drive cross-cutting side effects (cache invalidation,
metrics) that shouldn't block the original mutating request. This is a
legitimate, different pattern from Identity/Products' "we consume
nothing" stance: it's Geo acting as its own asynchronous consumer, not
Geo depending on another bounded context's events. No OTHER module's
events are consumed here -- that would still require a Domain
Architecture Specification Communication Matrix amendment (MIC §7).

Cache helpers live in this file rather than a separate `cache.py`
because this phase's explicit file list (`models.py`, `repositories.py`,
`selectors.py`, `admin.py`, `signals.py`, `event_handlers.py`,
`tasks.py`, `health.py`, `apps.py`, `composition.py`) does not include
one -- adding an unlisted file would itself be a scope deviation from
this phase's own instructions.
"""
from __future__ import annotations

import uuid

from core.caching import cache_key, get_redis_client
from core.metrics import default_collector

_GEO_CACHE_NAMESPACE = "geo"

# Independently invalidatable cache groups, so e.g. creating a District
# doesn't have to bump the (much larger, more expensive to rebuild)
# Country Tree cache.
CACHE_GROUPS = (
    "country_tree", "region_tree", "district_tree", "city_list", "neighborhood_list",
    "hierarchy_tree", "address_lookup", "geo_search",
)


def geo_cache_key(group: str, *parts) -> str:
    if group not in CACHE_GROUPS:
        raise ValueError(f"Unknown geo cache group '{group}'. Must be one of {CACHE_GROUPS}.")
    version = _current_version(group)
    joined = ":".join(str(p) for p in parts)
    return f"nutrizone:{_GEO_CACHE_NAMESPACE}:{group}:v{version}:{joined}"


def _current_version(group: str) -> int:
    client = get_redis_client()
    raw = client.get(cache_key(group, namespace=f"{_GEO_CACHE_NAMESPACE}:version"))
    return int(raw) if raw is not None else 0


def invalidate_geo_scope(scope: str) -> None:
    """
    Bumps the version counter for every cache group affected by a
    mutation at the given scope -- e.g. invalidating "city" bumps
    city_list, hierarchy_tree, AND geo_search (a city name change
    affects all three), while "address" only bumps address_lookup.
    """
    client = get_redis_client()
    affected = _SCOPE_TO_GROUPS.get(scope, CACHE_GROUPS)
    for group in affected:
        client.incr(cache_key(group, namespace=f"{_GEO_CACHE_NAMESPACE}:version"))


_SCOPE_TO_GROUPS = {
    "country": ("country_tree", "hierarchy_tree", "geo_search"),
    "region": ("region_tree", "hierarchy_tree", "geo_search"),
    "district": ("district_tree", "hierarchy_tree", "geo_search"),
    "city": ("city_list", "hierarchy_tree", "geo_search"),
    "neighborhood": ("neighborhood_list", "hierarchy_tree", "geo_search"),
    "address": ("address_lookup",),
}


_EVENT_TO_CACHE_SCOPE = {
    "CountryCreated": "country",
    "RegionCreated": "region",
    "DistrictCreated": "district",
    "CityCreated": "city",
    "NeighborhoodCreated": "neighborhood",
    "AddressCreated": "address",
    "AddressUpdated": "address",
}

_EVENT_TO_METRIC = {
    "CountryCreated": "geo_countries_total",
    "RegionCreated": "geo_regions_total",
    "DistrictCreated": "geo_districts_total",
    "CityCreated": "geo_cities_total",
    "NeighborhoodCreated": "geo_neighborhoods_total",
    "AddressCreated": "geo_addresses_total",
}


def handle_geo_event(event_type: str, payload: dict) -> None:
    """
    Called by the Outbox relay task (infrastructure/tasks.py) for each
    of this schema's own events -- stages nothing further (the event
    was already staged by the emitting Application Service), just
    performs the listed side effects: invalidate cache, record
    metrics. Audit was already written synchronously by the emitting
    service (core.audit.AuditEventBuilder) -- this handler does not
    duplicate that write, only the two genuinely-safe-to-defer effects.
    """
    import logging

    logger = logging.getLogger("nutrizone.app")

    scope = _EVENT_TO_CACHE_SCOPE.get(event_type)
    if scope:
        invalidate_geo_scope(scope)

    metric_name = _EVENT_TO_METRIC.get(event_type)
    if metric_name:
        default_collector.counter(metric_name)

    logger.info("geo event handled: %s", event_type)
