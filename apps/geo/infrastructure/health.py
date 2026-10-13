"""
Geo & Location health checks -- registered against
`core.health.registry` from `apps/geo/apps.py`'s `ready()` hook,
matching the pattern established by `apps.identity`/`apps.products`.
`core/health/` never imports this module directly.
"""
from __future__ import annotations


def check_geo_repository() -> tuple[bool, str]:
    try:
        from apps.geo.infrastructure import models as orm

        orm.Country.objects.exists()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_geo_database() -> tuple[bool, str]:
    """Distinct from check_geo_repository: exercises a JOIN across the hierarchy (City -> Region -> Country) rather than a single-table query, per this phase's explicit 'Database Health' check."""
    try:
        from apps.geo.infrastructure import models as orm

        orm.City.objects.select_related("region__country").first()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_geo_cache() -> tuple[bool, str]:
    try:
        from core.caching import get_redis_client

        client = get_redis_client()
        client.set("_health_check:geo:probe", "ok", ex=5)
        result = client.get("_health_check:geo:probe")
        client.delete("_health_check:geo:probe")
        if result != "ok":
            return False, "cache round-trip returned unexpected content"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_geo_outbox() -> tuple[bool, str]:
    try:
        from apps.geo.infrastructure import models as orm

        pending = orm.GeoOutboxEvent.objects.filter(published_at__isnull=True).count()
        return True, f"ok ({pending} pending)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_geo_search() -> tuple[bool, str]:
    try:
        from apps.geo.infrastructure.selectors import DjangoGeoSearchBackend

        DjangoGeoSearchBackend().search(query="", geo_level=None, page=1, page_size=1)
        return True, "ok (Postgres translation-table search)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


