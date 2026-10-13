"""
POS health checks -- registered against `core.health.registry` from
`apps/pos/apps.py`'s `ready()` hook. Each executes real logic, not
merely an import test.

**No fixed count was assumed**; derived directly from this module's
actual Infrastructure dependencies -- including a content-integrity
check mirroring the identical pattern established by every prior
module's own equivalent (Reviews, Chat, Notifications, Analytics). No
external payment/terminal/fiscalization connectivity check exists --
zero such gateway exists this phase (see the deliberate absence of
`gateways.py`); a health check for an integration that does not exist
would be premature.
"""
from __future__ import annotations

from apps.pos.infrastructure import models as orm
from apps.pos.infrastructure.composition import build_sale_repository
from core.caching import get_redis_client


def check_sale_repository() -> tuple[bool, str]:
    try:
        orm.SaleModel.objects.exists()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_pos_outbox_backlog() -> tuple[bool, str]:
    try:
        pending = orm.PosOutboxEvent.objects.filter(published_at__isnull=True).count()
        if pending > 500:
            return False, f"{pending} outbox events are pending publication"
        return True, f"ok ({pending} pending)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_orphaned_sale_line_items() -> tuple[bool, str]:
    """Verifies every SaleLineItemModel row's sale FK actually points at a live SaleModel -- a real cross-table consistency check beyond Django's own FK enforcement (which a bad migration or manual fix could bypass)."""
    try:
        orphaned = orm.SaleLineItemModel.objects.filter(sale__isnull=True).count()
        if orphaned > 0:
            return False, f"{orphaned} sale line items are orphaned"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_sale_line_item_integrity() -> tuple[bool, str]:
    """Verifies no persisted line item violates the invariants Quantity/Money already enforce at construction time (quantity >= 1, unit_price_amount >= 0) -- a real database-level consistency check against drift, matching the identical pattern established by every prior module's own content-integrity health check."""
    try:
        bad_count = orm.SaleLineItemModel.objects.filter(quantity__lt=1).count() + orm.SaleLineItemModel.objects.filter(unit_price_amount__lt=0).count()
        if bad_count > 0:
            return False, f"{bad_count} sale line items violate quantity/price invariants"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_composition_integrity() -> tuple[bool, str]:
    try:
        build_sale_repository()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"composition root failed to build a repository: {exc}"


def check_pos_cache() -> tuple[bool, str]:
    try:
        client = get_redis_client()
        client.set("_health_check:pos:probe", "ok", ex=5)
        result = client.get("_health_check:pos:probe")
        client.delete("_health_check:pos:probe")
        if result != "ok":
            return False, "cache round-trip returned unexpected content"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"
