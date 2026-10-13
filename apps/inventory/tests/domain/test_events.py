from __future__ import annotations

import uuid

import pytest

from apps.inventory.domain.events import (
    BatchCreated,
    InventoryArchivedEvent,
    InventoryCreated,
    ReservationCreated,
    ReservationExpiredEvent,
    StockDamaged,
    StockExpired,
    StockReceived,
    StockTransferred,
)

pytestmark = pytest.mark.unit


def test_inventory_created_payload():
    pid = uuid.uuid4()
    vid = uuid.uuid4()
    payload = InventoryCreated(inventory_id=pid, code="WHEY001", product_variant_id=vid).to_payload()
    assert payload["inventory_id"] == str(pid)
    assert payload["product_variant_id"] == str(vid)


def test_inventory_archived_event_does_not_collide_with_exception_name():
    """The event is named InventoryArchivedEvent specifically to avoid colliding with the domain exception InventoryArchived -- verified here that both are importable simultaneously without conflict."""
    from apps.inventory.domain.exceptions import InventoryArchived

    event = InventoryArchivedEvent(inventory_id=uuid.uuid4())
    assert event.__class__.__name__ == "InventoryArchivedEvent"
    assert InventoryArchived.__name__ == "InventoryArchived"


def test_stock_received_payload():
    wid = uuid.uuid4()
    payload = StockReceived(warehouse_inventory_id=wid, quantity=10, reference="PO-001").to_payload()
    assert payload["quantity"] == 10


def test_stock_transferred_payload_has_both_endpoints():
    source, destination = uuid.uuid4(), uuid.uuid4()
    payload = StockTransferred(source_warehouse_inventory_id=source, destination_warehouse_inventory_id=destination, quantity=5).to_payload()
    assert payload["source_warehouse_inventory_id"] == str(source)
    assert payload["destination_warehouse_inventory_id"] == str(destination)


def test_stock_expired_handles_null_batch():
    payload = StockExpired(warehouse_inventory_id=uuid.uuid4(), quantity=5, batch_id=None).to_payload()
    assert payload["batch_id"] is None


def test_batch_created_payload():
    bid, iid = uuid.uuid4(), uuid.uuid4()
    payload = BatchCreated(batch_id=bid, inventory_id=iid, batch_number="BATCH-001").to_payload()
    assert payload["batch_number"] == "BATCH-001"


def test_reservation_created_payload():
    rid, wid = uuid.uuid4(), uuid.uuid4()
    payload = ReservationCreated(reservation_id=rid, reservation_number="RSV-ABC123", warehouse_inventory_id=wid).to_payload()
    assert payload["reservation_number"] == "RSV-ABC123"


def test_events_are_frozen():
    event = StockDamaged(warehouse_inventory_id=uuid.uuid4(), quantity=5)
    with pytest.raises(Exception):
        event.quantity = 10  # type: ignore[misc]
