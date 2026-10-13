"""
Products-specific health checks -- registered against
`core.health.registry` from `apps/products/apps.py`'s `ready()` hook,
matching the pattern established by
`apps/identity/infrastructure/health.py`. `core/health/` never imports
this module directly (dependency direction preserved, per
`core/health/registry.py`'s own docstring).
"""
from __future__ import annotations


def check_products_repository() -> tuple[bool, str]:
    try:
        from apps.products.infrastructure import models as orm

        orm.Product.objects.exists()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_products_media_storage() -> tuple[bool, str]:
    try:
        from core.storage import get_storage_backend

        backend = get_storage_backend()
        probe_path = "_health_check/products_probe.txt"
        backend.save(probe_path, b"ok")
        content = backend.read(probe_path)
        backend.delete(probe_path)
        if content != b"ok":
            return False, "storage round-trip returned unexpected content"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_products_search() -> tuple[bool, str]:
    try:
        from apps.products.infrastructure.selectors import DjangoProductSearchBackend

        DjangoProductSearchBackend().search(query="", filters={}, page=1, page_size=1, sort="-created_at")
        return True, "ok (Postgres full-text search)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_products_cache() -> tuple[bool, str]:
    try:
        from core.caching import CacheDomain, CacheManager

        manager = CacheManager(CacheDomain.PRODUCT)
        manager.set("_health_check", "probe", value={"ok": True}, ttl_override=5)
        result = manager.get("_health_check", "probe")
        manager.delete("_health_check", "probe")
        if result != {"ok": True}:
            return False, "cache round-trip returned unexpected content"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_products_outbox() -> tuple[bool, str]:
    try:
        from apps.products.infrastructure import models as orm

        pending = orm.ProductsOutboxEvent.objects.filter(published_at__isnull=True).count()
        return True, f"ok ({pending} pending)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_products_event_registration() -> tuple[bool, str]:
    try:
        from core.events import registry

        expected = {"ProductCreated", "ProductPublished", "ProductHidden", "ProductArchived"}
        registered = set(registry.all_event_types())
        missing = expected - registered
        if missing:
            return False, f"missing event registrations: {sorted(missing)}"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"
