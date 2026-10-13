from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from apps.inventory.domain.entities import (
    BatchItem,
    InventoryHistory,
    InventoryLedger,
    InventoryTransaction,
    MovementItem,
    ReservationItem,
    SerialItem,
    StockAlert,
    StockSnapshot,
    ThresholdRule,
)
from apps.inventory.domain.enums import LedgerEntryType, SerialStatus, StockStatus
from apps.inventory.domain.value_objects import SerialNumber, StockQuantity

pytestmark = pytest.mark.unit


def test_inventory_ledger_entity_construction():
    entry = InventoryLedger(id=uuid.uuid4(), entry_type=LedgerEntryType.RECEIVE, stock_status=StockStatus.INCOMING, quantity_delta=10, balance_after=10, reference="PO-001", occurred_at=datetime.utcnow())
    assert entry.quantity_delta == 10
    assert entry.balance_after == 10


def test_inventory_transaction_entity_construction():
    transaction = InventoryTransaction(id=uuid.uuid4(), movement_type="receive", quantity=10, from_status=None, to_status=StockStatus.INCOMING, reference="PO-001", occurred_at=datetime.utcnow())
    assert transaction.to_status == StockStatus.INCOMING


def test_reservation_item_entity():
    item = ReservationItem(id=uuid.uuid4(), quantity=StockQuantity(5))
    assert item.quantity.value == 5
    assert item.batch_id is None


def test_batch_item_entity():
    item = BatchItem(id=uuid.uuid4(), warehouse_inventory_id=uuid.uuid4(), shelf_inventory_id=None, quantity=StockQuantity(20))
    assert item.quantity.value == 20


def test_serial_item_entity_default_status():
    item = SerialItem(id=uuid.uuid4(), serial_number=SerialNumber("SN00012345"))
    assert item.status == SerialStatus.IN_STOCK


def test_inventory_history_entity():
    history = InventoryHistory(id=uuid.uuid4(), description="Stock received", occurred_at=datetime.utcnow())
    assert history.actor_id is None


def test_stock_snapshot_entity():
    snapshot_item = StockSnapshot(id=uuid.uuid4(), inventory_id=uuid.uuid4(), quantities_by_status={"available": 10})
    assert snapshot_item.quantities_by_status["available"] == 10


def test_stock_alert_entity_default_unacknowledged():
    alert = StockAlert(id=uuid.uuid4(), health_status="low_stock", triggered_at=datetime.utcnow())
    assert alert.acknowledged is False


def test_threshold_rule_entity_platform_wide_default():
    rule = ThresholdRule(id=uuid.uuid4(), low_stock_at=10, reorder_at=5)
    assert rule.warehouse_id is None


def test_movement_item_entity():
    item = MovementItem(id=uuid.uuid4(), quantity=StockQuantity(7), batch_id=uuid.uuid4())
    assert item.quantity.value == 7
    assert item.batch_id is not None
