"""
Inventory Celery tasks -- orchestration only, per this phase's
explicit "no business logic, only orchestration" instruction: every
task below loads data, calls a real Application Service or domain
policy for the actual decision, and persists the result -- it never
decides anything itself.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone as django_timezone

from apps.inventory.infrastructure import models as orm
from apps.inventory.infrastructure.event_handlers import handle_inventory_event
from core.outbox import OutboxRelay


@shared_task(queue="scheduled", name="inventory.expire_reservations")
def expire_reservations() -> int:
    """Sweeps every PENDING/CONFIRMED reservation past its expires_at and calls the real ExpireReservation Application Service for each -- the task orchestrates the sweep, the service (built via composition.py) makes the actual domain decision."""
    from apps.inventory.infrastructure.composition import build_expire_reservation
    from apps.inventory.infrastructure.repositories import DjangoReservationRepository

    now = django_timezone.now()
    expired_reservations = DjangoReservationRepository().list_expired(now)
    count = 0
    for reservation in expired_reservations:
        try:
            build_expire_reservation().execute(reservation.id)
            count += 1
        except Exception:  # noqa: BLE001 - one failed expiry must not abort the sweep for the rest
            continue
    return count


@shared_task(queue="scheduled", name="inventory.expire_batches")
def expire_batches() -> int:
    """Sweeps every ACTIVE batch past its expiration_date -- marks it EXPIRED via the domain aggregate's own `mark_expired()` method (loaded, mutated, saved -- the task never sets `status` directly)."""
    from apps.inventory.infrastructure.repositories import DjangoBatchRepository

    today = django_timezone.now().date()
    repo = DjangoBatchRepository()
    rows = orm.BatchModel.objects.filter(status="active", expiration_date__isnull=False, expiration_date__lte=today)
    count = 0
    for row in rows:
        batch = repo.get_by_id(row.id)
        if batch is None:
            continue
        batch.mark_expired(today)
        repo.save(batch)
        count += 1
    return count


@shared_task(queue="bulk", name="inventory.generate_snapshots")
def generate_snapshots(warehouse_inventory_ids: list[str]) -> str:
    import uuid

    from apps.inventory.infrastructure.composition import build_create_snapshot

    build_create_snapshot().execute([uuid.UUID(wi_id) for wi_id in warehouse_inventory_ids])
    return "ok"


@shared_task(queue="scheduled", name="inventory.ledger_verification")
def ledger_verification() -> dict:
    """Runs RebuildLedger's balance-verification check across every WarehouseInventory/StockStatus pair with ledger entries -- reports (not silently fixes) any corruption found, per the domain's own `LedgerCorrupted` exception semantics."""
    from apps.inventory.infrastructure.composition import build_rebuild_ledger

    pairs = orm.InventoryLedgerModel.objects.values_list("warehouse_inventory_id", "stock_status").distinct()
    service = build_rebuild_ledger()
    results = {"checked": 0, "balanced": 0, "corrupted": []}
    for warehouse_inventory_id, stock_status in pairs:
        results["checked"] += 1
        if service.execute(warehouse_inventory_id, stock_status):
            results["balanced"] += 1
        else:
            results["corrupted"].append({"warehouse_inventory_id": str(warehouse_inventory_id), "stock_status": stock_status})
    return results


@shared_task(queue="scheduled", name="inventory.threshold_scan")
def threshold_scan() -> int:
    """Scans every ACTIVE inventory item with a configured threshold, raises a StockAlert (via the domain aggregate) if current health warrants one."""
    from apps.inventory.domain.services import InventoryHealthPolicy
    from apps.inventory.infrastructure.repositories import DjangoInventoryRepository, DjangoWarehouseInventoryRepository

    inventory_repo = DjangoInventoryRepository()
    wi_repo = DjangoWarehouseInventoryRepository()
    alert_count = 0

    for row in orm.InventoryModel.objects.filter(status="active", low_stock_at__isnull=False):
        inventory = inventory_repo.get_by_id(row.id)
        if inventory is None or inventory.threshold is None:
            continue
        total_available = sum(wi.available_quantity for wi in wi_repo.list_by_inventory(inventory.id))
        health = InventoryHealthPolicy.evaluate(total_available, inventory.threshold)
        if health.value in ("low_stock", "out_of_stock"):
            inventory.raise_alert(health.value, django_timezone.now())
            inventory_repo.save(inventory)
            alert_count += 1

    return alert_count


@shared_task(queue="scheduled", name="inventory.health_scan")
def inventory_health_scan() -> dict:
    """Computes and records the InventoryHealthStatus gauge for every active inventory item, for ops dashboards."""
    from apps.inventory.domain.services import InventoryHealthPolicy
    from apps.inventory.infrastructure.repositories import DjangoInventoryRepository, DjangoWarehouseInventoryRepository
    from core.metrics import default_collector

    inventory_repo = DjangoInventoryRepository()
    wi_repo = DjangoWarehouseInventoryRepository()
    counts: dict[str, int] = {}

    for row in orm.InventoryModel.objects.filter(status="active"):
        inventory = inventory_repo.get_by_id(row.id)
        if inventory is None:
            continue
        total_available = sum(wi.available_quantity for wi in wi_repo.list_by_inventory(inventory.id))
        health = InventoryHealthPolicy.evaluate(total_available, inventory.threshold)
        counts[health.value] = counts.get(health.value, 0) + 1

    for status, count in counts.items():
        default_collector.gauge("inventory_health_status_count", count, status=status)
    return counts


@shared_task(queue="scheduled", name="inventory.rebuild_statistics")
def rebuild_statistics() -> str:
    from apps.inventory.infrastructure.event_handlers import invalidate_inventory_cache_group

    invalidate_inventory_cache_group("warehouse_summary")
    invalidate_inventory_cache_group("stock_levels")
    return "ok"


@shared_task(queue="transactional", name="inventory.relay_outbox_events")
def relay_outbox_events() -> dict:
    """Celery Beat-scheduled Outbox relay for the `inventory` schema -- matches every prior module's identical relay task."""

    def _publish(event) -> bool:
        try:
            handle_inventory_event(event.event_type, event.payload)
            return True
        except Exception:  # noqa: BLE001
            return False

    relay = OutboxRelay(orm.InventoryOutboxEvent, max_attempts=5, batch_size=100)
    return relay.relay_pending(publish_fn=_publish)
