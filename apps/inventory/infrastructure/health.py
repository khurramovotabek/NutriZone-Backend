"""
Inventory health checks -- registered against `core.health.registry`
from `apps/inventory/apps.py`'s `ready()` hook, matching every prior
module's pattern. Each returns a structured `(bool, str)` result, per
this phase's "Return structured HealthResult" instruction (matching
the exact `(ok, detail)` tuple shape every prior module's health
checks already use, which `core.health`'s registry consumes uniformly).
"""
from __future__ import annotations


def check_inventory_repository() -> tuple[bool, str]:
    try:
        from apps.inventory.infrastructure import models as orm

        orm.InventoryModel.objects.exists()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_inventory_cache() -> tuple[bool, str]:
    try:
        from core.caching import get_redis_client

        client = get_redis_client()
        client.set("_health_check:inventory:probe", "ok", ex=5)
        result = client.get("_health_check:inventory:probe")
        client.delete("_health_check:inventory:probe")
        if result != "ok":
            return False, "cache round-trip returned unexpected content"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_inventory_ledger() -> tuple[bool, str]:
    """Verifies the ledger table is queryable AND spot-checks balance for one recent WarehouseInventory/StockStatus pair, rather than only checking table connectivity."""
    try:
        from apps.inventory.infrastructure import models as orm
        from apps.inventory.infrastructure.repositories import DjangoLedgerRepository
        from apps.inventory.domain.services import LedgerPolicy

        latest_entry = orm.InventoryLedgerModel.objects.order_by("-occurred_at").first()
        if latest_entry is None:
            return True, "ok (no ledger entries yet)"

        repo = DjangoLedgerRepository()
        entries = repo.list_entries(latest_entry.warehouse_inventory_id, stock_status=latest_entry.stock_status)
        claimed_balance = repo.get_latest_balance(latest_entry.warehouse_inventory_id, latest_entry.stock_status)
        deltas = [e["quantity_delta"] for e in entries]

        if not LedgerPolicy.verify_balance(deltas, claimed_balance):
            return False, "most recently touched ledger balance does not reconcile"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_inventory_snapshot() -> tuple[bool, str]:
    try:
        from apps.inventory.infrastructure import models as orm

        pending = orm.InventorySnapshotModel.objects.filter(status="pending").count()
        return True, f"ok ({pending} pending)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_inventory_batch() -> tuple[bool, str]:
    try:
        from django.utils import timezone as django_timezone

        from apps.inventory.infrastructure import models as orm

        expired_but_still_active = orm.BatchModel.objects.filter(status="active", expiration_date__isnull=False, expiration_date__lt=django_timezone.now().date()).count()
        if expired_but_still_active > 0:
            return False, f"{expired_but_still_active} batch(es) are past expiration but not yet marked EXPIRED (expire_batches task may be behind schedule)"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_inventory_reservation() -> tuple[bool, str]:
    try:
        from apps.inventory.infrastructure import models as orm
        from django.utils import timezone as django_timezone

        overdue = orm.ReservationModel.objects.filter(status__in=["pending", "confirmed"], expires_at__lt=django_timezone.now()).count()
        if overdue > 5:
            return False, f"{overdue} reservations are past expiration and not yet swept (expire_reservations task may be behind schedule)"
        return True, f"ok ({overdue} pending sweep)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"
