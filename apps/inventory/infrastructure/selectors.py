"""
Inventory read-model selectors -- optimized, read-only Postgres
queries. No business logic, matching the pattern established by every
prior module.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from django.db.models import Sum
from django.utils import timezone as django_timezone

from apps.inventory.domain.enums import InventoryStatus, ReservationStatus
from apps.inventory.infrastructure import models as orm

_STATUS_FIELDS = ("available_quantity", "reserved_quantity", "incoming_quantity", "damaged_quantity", "expired_quantity", "quarantine_quantity", "returned_quantity")


class InventorySelector:
    def list(self, status: str | None, query: str | None, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.InventoryModel.objects.all()
        if status:
            qs = qs.filter(status=status)
        if query:
            qs = qs.filter(code__icontains=query)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.order_by("code")[start : start + page_size]
        return [self._card(r) for r in rows], total

    def get_by_code(self, code: str) -> dict | None:
        row = orm.InventoryModel.objects.filter(code=code, status=InventoryStatus.ACTIVE.value).first()
        return self._card(row) if row else None

    def _card(self, row: orm.InventoryModel) -> dict:
        return {"id": str(row.id), "code": row.code, "product_variant_id": str(row.product_variant_id), "status": row.status, "is_batch_tracked": row.is_batch_tracked, "is_serial_tracked": row.is_serial_tracked}


class WarehouseSelector:
    """Summary statistics per warehouse -- backs the 'warehouse summary' selector requirement."""

    def summary(self, warehouse_id: uuid.UUID) -> dict:
        rows = orm.WarehouseInventoryModel.objects.filter(warehouse_id=warehouse_id)
        totals = {field: 0 for field in _STATUS_FIELDS}
        for row in rows:
            for field in _STATUS_FIELDS:
                totals[field] += getattr(row, field)
        return {"warehouse_id": str(warehouse_id), "item_count": rows.count(), **totals}


class StockSelector:
    """Backs 'low stock', 'expiring batches', 'reserved stock' selector requirements."""

    def low_stock(self, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        qs = orm.InventoryModel.objects.filter(status=InventoryStatus.ACTIVE.value, low_stock_at__isnull=False)
        results = []
        for row in qs:
            total_available = orm.WarehouseInventoryModel.objects.filter(inventory=row).aggregate(total=Sum("available_quantity"))["total"] or 0
            if total_available <= row.low_stock_at:
                results.append({"inventory_id": str(row.id), "code": row.code, "available_quantity": total_available, "low_stock_at": row.low_stock_at})
        total = len(results)
        start = (page - 1) * page_size
        return results[start : start + page_size], total

    def expiring_batches(self, within_days: int = 30) -> list[dict]:
        cutoff = django_timezone.now().date() + timedelta(days=within_days)
        rows = orm.BatchModel.objects.filter(status="active", expiration_date__isnull=False, expiration_date__lte=cutoff).order_by("expiration_date")
        return [{"batch_id": str(r.id), "batch_number": r.batch_number, "expiration_date": r.expiration_date.isoformat(), "quantity_received": r.quantity_received} for r in rows]

    def list_all(self, page: int = 1, page_size: int = 20, product_variant_ids: list | None = None) -> tuple[list[dict], int]:
        """
        Real, closed gap: the Inventory dashboard's own product/stock
        table needs every active inventory item's real per-warehouse
        breakdown, not just the ones already low on stock (`low_stock`
        above only ever returns items under their own threshold).
        Deliberately returns no product name/price/currency of its own
        -- Inventory never imports Products/Pricing (the established,
        one-directional dependency already followed by every prior
        selector here); the caller (apps/platform/infrastructure/
        inventory_view.py, which already freely imports both) resolves
        those and merges them in, exactly like it already does for
        `low_stock`'s own product-name column.

        `product_variant_ids`, when given, narrows to those variants
        only -- the caller's own real product-name/SKU search
        (Inventory has no name field of its own to search against).
        """
        qs = orm.InventoryModel.objects.filter(status=InventoryStatus.ACTIVE.value)
        if product_variant_ids is not None:
            qs = qs.filter(product_variant_id__in=product_variant_ids)
        qs = qs.order_by("code")
        total = qs.count()
        start = (page - 1) * page_size
        rows = list(qs[start : start + page_size])

        warehouse_rows = orm.WarehouseInventoryModel.objects.filter(inventory_id__in=[r.id for r in rows]).values("id", "inventory_id", "warehouse_id", "available_quantity")
        by_inventory: dict = {}
        for wr in warehouse_rows:
            by_inventory.setdefault(wr["inventory_id"], []).append({"warehouse_inventory_id": str(wr["id"]), "warehouse_id": str(wr["warehouse_id"]), "available_quantity": wr["available_quantity"]})

        results = []
        for row in rows:
            breakdown = by_inventory.get(row.id, [])
            results.append({
                "inventory_id": str(row.id), "code": row.code, "product_variant_id": str(row.product_variant_id),
                "total_available": sum(b["available_quantity"] for b in breakdown),
                "by_warehouse": breakdown,
            })
        return results, total

    def system_totals(self) -> dict:
        """Real, closed gap: the dashboard's own top-level KPIs -- how many distinct warehouses exist, and how many real units sit in stock across the whole system (never per-warehouse alone) -- backed by one real aggregate query each, not a fabricated round number."""
        rows = orm.WarehouseInventoryModel.objects.values("warehouse_id").annotate(total=Sum("available_quantity")).order_by("warehouse_id")
        by_warehouse = {str(r["warehouse_id"]): r["total"] or 0 for r in rows}
        return {"by_warehouse": by_warehouse, "total_units": sum(by_warehouse.values())}

    def reserved_stock(self, warehouse_id: uuid.UUID | None = None) -> list[dict]:
        qs = orm.WarehouseInventoryModel.objects.filter(reserved_quantity__gt=0)
        if warehouse_id:
            qs = qs.filter(warehouse_id=warehouse_id)
        return [{"warehouse_inventory_id": str(r.id), "inventory_id": str(r.inventory_id), "warehouse_id": str(r.warehouse_id), "reserved_quantity": r.reserved_quantity} for r in qs]


class ReservationSelector:
    def list_active(self, owner_type: str | None = None, owner_id: uuid.UUID | None = None) -> list[dict]:
        qs = orm.ReservationModel.objects.filter(status__in=[ReservationStatus.PENDING.value, ReservationStatus.CONFIRMED.value])
        if owner_type:
            qs = qs.filter(owner_type=owner_type)
        if owner_id:
            qs = qs.filter(owner_id=owner_id)
        return [{"id": str(r.id), "reservation_number": r.reservation_number, "status": r.status, "expires_at": r.expires_at.isoformat() if r.expires_at else None} for r in qs]


class LedgerSelector:
    def list_entries(self, warehouse_inventory_id: uuid.UUID, page: int = 1, page_size: int = 50) -> tuple[list[dict], int]:
        qs = orm.InventoryLedgerModel.objects.filter(warehouse_inventory_id=warehouse_inventory_id).order_by("-occurred_at")
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs[start : start + page_size]
        return [{"id": str(r.id), "entry_type": r.entry_type, "stock_status": r.stock_status, "quantity_delta": r.quantity_delta, "balance_after": r.balance_after, "occurred_at": r.occurred_at.isoformat()} for r in rows], total


class BatchSelector:
    def list_by_inventory(self, inventory_id: uuid.UUID) -> list[dict]:
        rows = orm.BatchModel.objects.filter(inventory_id=inventory_id).order_by("expiration_date")
        return [{"id": str(r.id), "batch_number": r.batch_number, "status": r.status, "expiration_date": r.expiration_date.isoformat() if r.expiration_date else None, "quantity_received": r.quantity_received} for r in rows]


class SnapshotSelector:
    def list_recent(self, limit: int = 20) -> list[dict]:
        rows = orm.InventorySnapshotModel.objects.order_by("-version")[:limit]
        return [{"id": str(r.id), "version": r.version, "status": r.status, "captured_at": r.captured_at.isoformat() if r.captured_at else None} for r in rows]


class CycleCountSelector:
    def list_by_warehouse(self, warehouse_id: uuid.UUID) -> list[dict]:
        rows = orm.CycleCountModel.objects.filter(warehouse_id=warehouse_id).order_by("-created_at")
        return [{"id": str(r.id), "status": r.status, "created_at": r.created_at.isoformat()} for r in rows]


class PhysicalInventorySelector:
    def list_by_warehouse(self, warehouse_id: uuid.UUID) -> list[dict]:
        rows = orm.PhysicalInventoryModel.objects.filter(warehouse_id=warehouse_id).order_by("-created_at")
        return [{"id": str(r.id), "status": r.status, "created_at": r.created_at.isoformat()} for r in rows]


class DjangoInventorySearchBackend:
    """Implements `application/ports.py::InventorySearchGateway` -- Postgres ILIKE search over inventory code, per every other module's identical launch-stage search approach."""

    def search(self, query: str, filters: dict, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.InventoryModel.objects.filter(status=InventoryStatus.ACTIVE.value)
        if query:
            qs = qs.filter(code__icontains=query)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.order_by("code")[start : start + page_size]
        return [{"id": str(r.id), "code": r.code, "status": r.status} for r in rows], total
