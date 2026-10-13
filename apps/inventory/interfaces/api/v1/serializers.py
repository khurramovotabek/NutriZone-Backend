"""
Inventory API serializers.

Structural validation only -- format checks delegate to the same
domain value objects used elsewhere (InventoryCode, BatchNumber,
SerialNumber, ReservationNumber), per MIC §6's "one place" rule.
Matches every prior module's `interfaces/api/v1/serializers.py`
pattern.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.inventory.domain.enums import (
    AdjustmentReason,
    BatchStatus,
    CycleCountStatus,
    InventoryStatus,
    MovementType,
    PhysicalInventoryStatus,
    ReservationStatus,
    SerialStatus,
    StockStatus,
)
from apps.inventory.domain.value_objects import BatchNumber, InventoryCode, ReservationNumber, SerialNumber
from common.exceptions import ValidationFailed


def _validate_inventory_code(value: str) -> str:
    try:
        InventoryCode(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


def _validate_batch_number(value: str) -> str:
    try:
        BatchNumber(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


def _validate_serial_number(value: str) -> str:
    try:
        SerialNumber(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


def _validate_reservation_number(value: str) -> str:
    try:
        ReservationNumber(value)
    except ValidationFailed as exc:
        raise serializers.ValidationError(exc.message) from exc
    return value


# --- Read shapes -----------------------------------------------------


class InventorySerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    product_variant_id = serializers.CharField()
    status = serializers.CharField()
    is_batch_tracked = serializers.BooleanField()
    is_serial_tracked = serializers.BooleanField()


class WarehouseInventorySerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    inventory_id = serializers.CharField()
    warehouse_id = serializers.CharField()
    available_quantity = serializers.IntegerField(read_only=True)
    reserved_quantity = serializers.IntegerField(read_only=True)
    incoming_quantity = serializers.IntegerField(read_only=True)
    damaged_quantity = serializers.IntegerField(read_only=True)
    expired_quantity = serializers.IntegerField(read_only=True)
    quarantine_quantity = serializers.IntegerField(read_only=True)
    returned_quantity = serializers.IntegerField(read_only=True)


class ShelfInventorySerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    warehouse_inventory_id = serializers.CharField()
    shelf_id = serializers.CharField()
    quantity = serializers.IntegerField(read_only=True)


class ReservationItemSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    quantity = serializers.IntegerField()
    batch_id = serializers.CharField(allow_null=True, required=False)


class ReservationSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    reservation_number = serializers.CharField()
    owner_type = serializers.CharField()
    owner_id = serializers.CharField()
    warehouse_inventory_id = serializers.CharField()
    status = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(allow_null=True, required=False)
    items = ReservationItemSerializer(many=True, required=False)


class MovementItemSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    quantity = serializers.IntegerField()
    batch_id = serializers.CharField(allow_null=True, required=False)


class InventoryMovementSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    movement_type = serializers.ChoiceField(choices=MovementType.values())
    reference = serializers.CharField()
    source_warehouse_inventory_id = serializers.CharField(allow_null=True, required=False)
    destination_warehouse_inventory_id = serializers.CharField(allow_null=True, required=False)
    items = MovementItemSerializer(many=True, required=False)
    occurred_at = serializers.DateTimeField(read_only=True)


class InventoryAdjustmentSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    warehouse_inventory_id = serializers.CharField()
    reason = serializers.ChoiceField(choices=AdjustmentReason.values())
    quantity_delta = serializers.IntegerField()
    reference = serializers.CharField()
    stock_status = serializers.ChoiceField(choices=StockStatus.values(), default=StockStatus.AVAILABLE.value)


class BatchSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    inventory_id = serializers.CharField()
    batch_number = serializers.CharField()
    manufacture_date = serializers.DateField(allow_null=True, required=False)
    expiration_date = serializers.DateField(allow_null=True, required=False)
    status = serializers.CharField(read_only=True)
    quantity_received = serializers.IntegerField(read_only=True)


class SerialSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    serial_number = serializers.CharField()
    status = serializers.ChoiceField(choices=SerialStatus.values(), default=SerialStatus.IN_STOCK.value)


class InventoryLedgerSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    entry_type = serializers.CharField(read_only=True)
    stock_status = serializers.CharField(read_only=True)
    quantity_delta = serializers.IntegerField(read_only=True)
    balance_after = serializers.IntegerField(read_only=True)
    occurred_at = serializers.DateTimeField(read_only=True)


class SnapshotItemSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    inventory_id = serializers.CharField()
    quantities_by_status = serializers.DictField(child=serializers.IntegerField())


class InventorySnapshotSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    version = serializers.IntegerField(read_only=True)
    status = serializers.ChoiceField(choices=["pending", "completed", "failed"], read_only=True)
    captured_at = serializers.DateTimeField(allow_null=True, read_only=True)


class CycleCountItemSerializer(serializers.Serializer):
    inventory_id = serializers.CharField()
    counted_quantity = serializers.IntegerField(min_value=0)


class CycleCountSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    warehouse_id = serializers.CharField()
    status = serializers.ChoiceField(choices=CycleCountStatus.values(), read_only=True)


class PhysicalInventoryItemSerializer(serializers.Serializer):
    inventory_id = serializers.CharField()
    counted_quantity = serializers.IntegerField(min_value=0)


class PhysicalInventorySerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    warehouse_id = serializers.CharField()
    status = serializers.ChoiceField(choices=PhysicalInventoryStatus.values(), read_only=True)


class InventoryHistorySerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    occurred_at = serializers.DateTimeField(read_only=True)
    actor_id = serializers.CharField(allow_null=True, read_only=True)


class StockAlertSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    health_status = serializers.CharField(read_only=True)
    triggered_at = serializers.DateTimeField(read_only=True)
    acknowledged = serializers.BooleanField()


class ThresholdRuleSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    low_stock_at = serializers.IntegerField(min_value=0)
    reorder_at = serializers.IntegerField(min_value=0)
    overstock_at = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    warehouse_id = serializers.CharField(allow_null=True, required=False)


# --- Request / command DTOs ------------------------------------------


class CreateInventorySerializer(serializers.Serializer):
    code = serializers.CharField(validators=[_validate_inventory_code])
    product_variant_id = serializers.UUIDField()
    is_batch_tracked = serializers.BooleanField(default=False)
    is_serial_tracked = serializers.BooleanField(default=False)


class UpdateInventorySerializer(serializers.Serializer):
    low_stock_at = serializers.IntegerField(required=False, min_value=0)
    reorder_at = serializers.IntegerField(required=False, min_value=0)
    overstock_at = serializers.IntegerField(required=False, allow_null=True, min_value=0)


class ReceiveStockSerializer(serializers.Serializer):
    warehouse_inventory_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    reference = serializers.CharField()


class ConfirmIncomingStockSerializer(serializers.Serializer):
    warehouse_inventory_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    reference = serializers.CharField()


class ReserveStockSerializer(serializers.Serializer):
    warehouse_inventory_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    reference = serializers.CharField()


class ReleaseReservationRequestSerializer(serializers.Serializer):
    warehouse_inventory_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    reference = serializers.CharField()


class TransferStockSerializer(serializers.Serializer):
    source_warehouse_inventory_id = serializers.UUIDField()
    destination_warehouse_inventory_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    reference = serializers.CharField()


class AdjustStockSerializer(serializers.Serializer):
    warehouse_inventory_id = serializers.UUIDField()
    stock_status = serializers.ChoiceField(choices=StockStatus.values())
    quantity_delta = serializers.IntegerField()
    reason = serializers.ChoiceField(choices=AdjustmentReason.values())
    reference = serializers.CharField()


class DamageStockSerializer(serializers.Serializer):
    warehouse_inventory_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    reference = serializers.CharField()


class ExpireStockSerializer(serializers.Serializer):
    warehouse_inventory_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    reference = serializers.CharField()
    batch_id = serializers.UUIDField(required=False, allow_null=True)


class CreateBatchSerializer(serializers.Serializer):
    inventory_id = serializers.UUIDField()
    batch_number = serializers.CharField(validators=[_validate_batch_number])
    manufacture_date = serializers.DateField(required=False, allow_null=True)
    expiration_date = serializers.DateField(required=False, allow_null=True)


class UpdateBatchSerializer(serializers.Serializer):
    expiration_date = serializers.DateField(required=False, allow_null=True)


class RegisterSerialSerializer(serializers.Serializer):
    serial_number = serializers.CharField(validators=[_validate_serial_number])


class CreateReservationSerializer(serializers.Serializer):
    reservation_number = serializers.CharField(validators=[_validate_reservation_number])
    owner_type = serializers.CharField(max_length=32)
    owner_id = serializers.UUIDField()
    warehouse_inventory_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    expires_in_minutes = serializers.IntegerField(required=False, min_value=1)


class CompleteCountSerializer(serializers.Serializer):
    """Shared shape for CompleteCycleCount/CompletePhysicalInventory -- both take the same 'counted quantities by inventory item' payload."""

    counted_quantities = serializers.DictField(child=serializers.IntegerField(min_value=0))


class CreateSnapshotSerializer(serializers.Serializer):
    warehouse_inventory_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1)


class RestoreSnapshotSerializer(serializers.Serializer):
    warehouse_id = serializers.UUIDField()
