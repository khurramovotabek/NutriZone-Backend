"""
Inventory ORM models.

Maps 1:1 onto the 19 tables this phase's brief requires. Every model
composes from exactly one of common/models/'s three base mixins per
the model-category decision tree in the Universal Module
Implementation Contract §3 -- reusing the exact platform base classes,
never redefining them.

Cross-module references (WarehouseInventory.warehouse_id ->
store.Warehouse, Inventory.product_variant_id ->
products.ProductVariant) are plain UUIDField columns, never a
ForeignKey across schemas -- the same modular-monolith rule already
applied consistently in every prior module.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.inventory.domain.enums import (
    AdjustmentReason,
    BatchStatus,
    CycleCountStatus,
    InventorySnapshotStatus,
    InventoryStatus,
    LedgerEntryType,
    MovementType,
    PhysicalInventoryStatus,
    ReservationStatus,
    SerialStatus,
    StockStatus,
)
from common.models import AllObjectsManager, BaseModel, SoftDeleteModel
from common.utils import enum_field_kwargs
from core.outbox import AbstractOutboxEvent


class InventoryModel(SoftDeleteModel):
    code = models.CharField(max_length=20, unique=True, db_index=True)
    product_variant_id = models.UUIDField(unique=True, db_index=True)
    status = models.CharField(default=InventoryStatus.ACTIVE.value, db_index=True, **enum_field_kwargs(InventoryStatus))
    is_batch_tracked = models.BooleanField(default=False)
    is_serial_tracked = models.BooleanField(default=False)
    low_stock_at = models.PositiveIntegerField(null=True, blank=True)
    reorder_at = models.PositiveIntegerField(null=True, blank=True)
    overstock_at = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "inventory_items"
        verbose_name=_("Inventory Item")
        verbose_name_plural = _("Inventory Items")
        indexes = [models.Index(fields=["status"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reorder_at__isnull=True) | models.Q(low_stock_at__isnull=True) | models.Q(reorder_at__lte=models.F("low_stock_at")),
                name="ck_inventory_items_reorder_le_low_stock",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.code


class WarehouseInventoryModel(BaseModel):
    inventory = models.ForeignKey(InventoryModel, on_delete=models.CASCADE, related_name="warehouse_inventories")
    warehouse_id = models.UUIDField(db_index=True)
    available_quantity = models.IntegerField(default=0)
    reserved_quantity = models.IntegerField(default=0)
    incoming_quantity = models.IntegerField(default=0)
    damaged_quantity = models.IntegerField(default=0)
    expired_quantity = models.IntegerField(default=0)
    quarantine_quantity = models.IntegerField(default=0)
    returned_quantity = models.IntegerField(default=0)

    class Meta:
        db_table = "inventory_warehouse_inventories"
        verbose_name=_("Warehouse Inventory")
        verbose_name_plural = _("Warehouse Inventories")
        constraints = [
            models.UniqueConstraint(fields=["inventory", "warehouse_id"], name="uq_warehouse_inventory_item_warehouse"),
            models.CheckConstraint(condition=models.Q(available_quantity__gte=0), name="ck_warehouse_inv_available_non_negative"),
            models.CheckConstraint(condition=models.Q(reserved_quantity__gte=0), name="ck_warehouse_inv_reserved_non_negative"),
            models.CheckConstraint(condition=models.Q(incoming_quantity__gte=0), name="ck_warehouse_inv_incoming_non_negative"),
            models.CheckConstraint(condition=models.Q(damaged_quantity__gte=0), name="ck_warehouse_inv_damaged_non_negative"),
            models.CheckConstraint(condition=models.Q(expired_quantity__gte=0), name="ck_warehouse_inv_expired_non_negative"),
            models.CheckConstraint(condition=models.Q(quarantine_quantity__gte=0), name="ck_warehouse_inv_quarantine_non_negative"),
            models.CheckConstraint(condition=models.Q(returned_quantity__gte=0), name="ck_warehouse_inv_returned_non_negative"),
        ]
        indexes = [models.Index(fields=["warehouse_id"]), models.Index(fields=["inventory", "warehouse_id"])]


class ShelfInventoryModel(BaseModel):
    warehouse_inventory = models.ForeignKey(WarehouseInventoryModel, on_delete=models.CASCADE, related_name="shelf_inventories")
    shelf_id = models.UUIDField(db_index=True)
    quantity = models.IntegerField(default=0)

    class Meta:
        db_table = "inventory_shelf_inventories"
        verbose_name=_("Shelf Inventory")
        verbose_name_plural = _("Shelf Inventories")
        constraints = [
            models.UniqueConstraint(fields=["warehouse_inventory", "shelf_id"], name="uq_shelf_inventory_warehouse_inv_shelf"),
            models.CheckConstraint(condition=models.Q(quantity__gte=0), name="ck_shelf_inventory_quantity_non_negative"),
        ]


class BatchModel(SoftDeleteModel):
    inventory = models.ForeignKey(InventoryModel, on_delete=models.CASCADE, related_name="batches")
    batch_number = models.CharField(max_length=48, unique=True, db_index=True)
    manufacture_date = models.DateField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)
    status = models.CharField(default=BatchStatus.ACTIVE.value, db_index=True, **enum_field_kwargs(BatchStatus))
    quantity_received = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "inventory_batches"
        verbose_name=_("Batch")
        verbose_name_plural = _("Batches")
        indexes = [models.Index(fields=["inventory", "status"]), models.Index(fields=["expiration_date"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(manufacture_date__isnull=True) | models.Q(expiration_date__isnull=True) | models.Q(expiration_date__gt=models.F("manufacture_date")),
                name="ck_batches_expiration_after_manufacture",
            ),
        ]


class SerialModel(SoftDeleteModel):
    batch = models.ForeignKey(BatchModel, on_delete=models.CASCADE, related_name="serials")
    serial_number = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(default=SerialStatus.IN_STOCK.value, **enum_field_kwargs(SerialStatus))

    class Meta:
        db_table = "inventory_serials"
        verbose_name=_("Serial")
        verbose_name_plural = _("Serials")
        indexes = [models.Index(fields=["batch"])]


class ReservationModel(BaseModel):
    reservation_number = models.CharField(max_length=32, unique=True, db_index=True)
    owner_type = models.CharField(max_length=32, db_index=True)
    owner_id = models.UUIDField(db_index=True)
    warehouse_inventory = models.ForeignKey(WarehouseInventoryModel, on_delete=models.PROTECT, related_name="reservations")
    status = models.CharField(default=ReservationStatus.PENDING.value, db_index=True, **enum_field_kwargs(ReservationStatus))
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "inventory_reservations"
        verbose_name=_("Reservation")
        verbose_name_plural = _("Reservations")
        indexes = [models.Index(fields=["owner_type", "owner_id"]), models.Index(fields=["status", "expires_at"])]


class ReservationItemModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    reservation = models.ForeignKey(ReservationModel, on_delete=models.CASCADE, related_name="items")
    quantity = models.PositiveIntegerField()
    batch = models.ForeignKey(BatchModel, on_delete=models.PROTECT, null=True, blank=True, related_name="reservation_items")

    objects = AllObjectsManager()

    class Meta:
        db_table = "inventory_reservation_items"
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="ck_reservation_items_quantity_positive")]


class InventoryMovementModel(BaseModel):
    movement_type = models.CharField(db_index=True, **enum_field_kwargs(MovementType))
    reference = models.CharField(max_length=32, db_index=True)
    source_warehouse_inventory = models.ForeignKey(WarehouseInventoryModel, on_delete=models.PROTECT, null=True, blank=True, related_name="outgoing_movements")
    destination_warehouse_inventory = models.ForeignKey(WarehouseInventoryModel, on_delete=models.PROTECT, null=True, blank=True, related_name="incoming_movements")
    occurred_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "inventory_movements"
        verbose_name=_("Inventory Movement")
        verbose_name_plural = _("Inventory Movements")
        indexes = [models.Index(fields=["movement_type", "occurred_at"])]


class MovementItemModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    movement = models.ForeignKey(InventoryMovementModel, on_delete=models.CASCADE, related_name="items")
    quantity = models.PositiveIntegerField()
    batch = models.ForeignKey(BatchModel, on_delete=models.PROTECT, null=True, blank=True, related_name="movement_items")

    objects = AllObjectsManager()

    class Meta:
        db_table = "inventory_movement_items"
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="ck_movement_items_quantity_positive")]


class InventoryAdjustmentModel(BaseModel):
    warehouse_inventory = models.ForeignKey(WarehouseInventoryModel, on_delete=models.PROTECT, related_name="adjustments")
    reason = models.CharField(**enum_field_kwargs(AdjustmentReason))
    quantity_delta = models.IntegerField()
    reference = models.CharField(max_length=64)
    stock_status = models.CharField(default=StockStatus.AVAILABLE.value, **enum_field_kwargs(StockStatus))

    class Meta:
        db_table = "inventory_adjustments"
        verbose_name=_("Inventory Adjustment")
        verbose_name_plural = _("Inventory Adjustments")
        constraints = [models.CheckConstraint(condition=~models.Q(quantity_delta=0), name="ck_adjustments_delta_non_zero")]


class InventoryLedgerModel(models.Model):
    """Append-only journal -- deliberately NOT built on AbstractOutboxEvent (that's for cross-module event publishing, this is an accounting record); modeled as a plain, insert-only Model with no update/delete path exposed by its repository (infrastructure/repositories.py enforces this at the Python level, matching Database Blueprint §3's append-only discipline for tables that aren't literally the Outbox)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    warehouse_inventory = models.ForeignKey(WarehouseInventoryModel, on_delete=models.PROTECT, related_name="ledger_entries")
    entry_type = models.CharField(**enum_field_kwargs(LedgerEntryType))
    stock_status = models.CharField(**enum_field_kwargs(StockStatus))
    quantity_delta = models.IntegerField()
    balance_after = models.IntegerField()
    reference = models.CharField(max_length=64)
    occurred_at = models.DateTimeField(db_index=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "inventory_ledger_entries"
        verbose_name=_("Ledger Entry")
        verbose_name_plural = _("Ledger Entries")
        indexes = [models.Index(fields=["warehouse_inventory", "stock_status", "occurred_at"])]
        constraints = [models.CheckConstraint(condition=models.Q(balance_after__gte=0), name="ck_ledger_balance_non_negative")]


class InventoryTransactionModel(models.Model):
    """Backs `domain.entities.InventoryTransaction` -- the 'what happened' record paired 1:1 with the ledger entries a WarehouseInventory method call produces."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    warehouse_inventory = models.ForeignKey(WarehouseInventoryModel, on_delete=models.PROTECT, related_name="transactions")
    movement_type = models.CharField(max_length=32)
    quantity = models.PositiveIntegerField()
    from_status = models.CharField(max_length=32, null=True, blank=True)
    to_status = models.CharField(max_length=32, null=True, blank=True)
    reference = models.CharField(max_length=64)
    occurred_at = models.DateTimeField(db_index=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "inventory_transactions"


class InventorySnapshotModel(BaseModel):
    version = models.PositiveIntegerField(unique=True, db_index=True)
    status = models.CharField(default=InventorySnapshotStatus.PENDING.value, **enum_field_kwargs(InventorySnapshotStatus))
    captured_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "inventory_snapshots"
        verbose_name=_("Inventory Snapshot")
        verbose_name_plural = _("Inventory Snapshots")


class SnapshotItemModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    snapshot = models.ForeignKey(InventorySnapshotModel, on_delete=models.CASCADE, related_name="items")
    inventory_id = models.UUIDField(db_index=True)
    quantities_by_status = models.JSONField(default=dict)

    objects = AllObjectsManager()

    class Meta:
        db_table = "inventory_snapshot_items"
        constraints = [models.UniqueConstraint(fields=["snapshot", "inventory_id"], name="uq_snapshot_items_snapshot_inventory")]


class CycleCountModel(BaseModel):
    warehouse_id = models.UUIDField(db_index=True)
    status = models.CharField(default=CycleCountStatus.PLANNED.value, db_index=True, **enum_field_kwargs(CycleCountStatus))

    class Meta:
        db_table = "inventory_cycle_counts"
        verbose_name=_("Cycle Count")
        verbose_name_plural = _("Cycle Counts")


class CycleCountItemModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    cycle_count = models.ForeignKey(CycleCountModel, on_delete=models.CASCADE, related_name="items")
    inventory_id = models.UUIDField(db_index=True)
    counted_quantity = models.PositiveIntegerField()

    objects = AllObjectsManager()

    class Meta:
        db_table = "inventory_cycle_count_items"
        constraints = [models.UniqueConstraint(fields=["cycle_count", "inventory_id"], name="uq_cycle_count_items_count_inventory")]


class PhysicalInventoryModel(BaseModel):
    warehouse_id = models.UUIDField(db_index=True)
    status = models.CharField(default=PhysicalInventoryStatus.PLANNED.value, db_index=True, **enum_field_kwargs(PhysicalInventoryStatus))

    class Meta:
        db_table = "inventory_physical_inventories"
        verbose_name=_("Physical Inventory")
        verbose_name_plural=_("Physical Inventories")


class PhysicalInventoryItemModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    physical_inventory = models.ForeignKey(PhysicalInventoryModel, on_delete=models.CASCADE, related_name="items")
    inventory_id = models.UUIDField(db_index=True)
    counted_quantity = models.PositiveIntegerField()

    objects = AllObjectsManager()

    class Meta:
        db_table = "inventory_physical_inventory_items"
        constraints = [models.UniqueConstraint(fields=["physical_inventory", "inventory_id"], name="uq_physical_inv_items_pi_inventory")]


class InventoryHistoryModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    inventory = models.ForeignKey(InventoryModel, on_delete=models.CASCADE, related_name="history_entries")
    description = models.CharField(max_length=512)
    occurred_at = models.DateTimeField(db_index=True)
    actor_id = models.UUIDField(null=True, blank=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "inventory_history"
        verbose_name=_("Inventory History")
        verbose_name_plural=_("Inventory History")


class StockAlertModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    inventory = models.ForeignKey(InventoryModel, on_delete=models.CASCADE, related_name="alerts")
    health_status = models.CharField(max_length=32)
    triggered_at = models.DateTimeField(db_index=True)
    acknowledged = models.BooleanField(default=False)

    objects = AllObjectsManager()

    class Meta:
        db_table = "inventory_stock_alerts"
        verbose_name=_("Stock Alert")
        verbose_name_plural = _("Stock Alerts")


class ThresholdRuleModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    inventory = models.ForeignKey(InventoryModel, on_delete=models.CASCADE, related_name="threshold_rules")
    low_stock_at = models.PositiveIntegerField()
    reorder_at = models.PositiveIntegerField()
    overstock_at = models.PositiveIntegerField(null=True, blank=True)
    warehouse_id = models.UUIDField(null=True, blank=True, db_index=True)  # None = platform-wide default

    objects = AllObjectsManager()

    class Meta:
        db_table = "inventory_threshold_rules"
        verbose_name=_("Threshold Rule")
        verbose_name_plural = _("Threshold Rules")
        constraints = [models.CheckConstraint(condition=models.Q(reorder_at__lte=models.F("low_stock_at")), name="ck_threshold_rules_reorder_le_low_stock")]


class InventoryOutboxEvent(AbstractOutboxEvent):
    class Meta:
        db_table = "inventory_outbox_events"
        ordering = ["created_at"]


class StockTransferModel(models.Model):
    """One branch-to-branch transfer document (see apps/inventory/domain/transfers.py). Stock itself moves through the WarehouseInventory ledger; this row is the human-readable record of who moved what, where and when."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sequence = models.PositiveIntegerField(unique=True)
    number = models.CharField(max_length=20, unique=True, db_index=True, verbose_name=_("Number"))
    source_warehouse_id = models.UUIDField(db_index=True, verbose_name=_("From branch"))
    destination_warehouse_id = models.UUIDField(db_index=True, verbose_name=_("To branch"))
    note = models.CharField(max_length=500, blank=True, default="", verbose_name=_("Note"))
    actor_id = models.UUIDField(null=True, blank=True)
    actor_name = models.CharField(max_length=150, blank=True, default="", verbose_name=_("Sent by"))
    total_units = models.PositiveIntegerField(default=0, verbose_name=_("Units"))
    completed_at = models.DateTimeField(db_index=True, verbose_name=_("Date"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "inventory_stock_transfers"
        ordering = ["-completed_at"]
        verbose_name = _("Stock transfer")
        verbose_name_plural = _("Stock transfers")
        constraints = [models.CheckConstraint(condition=~models.Q(source_warehouse_id=models.F("destination_warehouse_id")), name="ck_stock_transfer_distinct_branches")]


class StockTransferLineModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transfer = models.ForeignKey(StockTransferModel, on_delete=models.CASCADE, related_name="lines")
    product_variant_id = models.UUIDField(db_index=True)
    quantity = models.PositiveIntegerField()
    source_warehouse_inventory = models.ForeignKey(WarehouseInventoryModel, on_delete=models.PROTECT, related_name="+")
    destination_warehouse_inventory = models.ForeignKey(WarehouseInventoryModel, on_delete=models.PROTECT, related_name="+")
    source_balance_after = models.IntegerField()
    destination_balance_after = models.IntegerField()

    class Meta:
        db_table = "inventory_stock_transfer_lines"
        verbose_name = _("Stock transfer line")
        verbose_name_plural = _("Stock transfer lines")
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0), name="ck_stock_transfer_lines_quantity_positive")]
