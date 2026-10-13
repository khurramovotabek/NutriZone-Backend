"""
In-memory fakes implementing application/ports.py's Protocols, matching
every prior module's `tests/application/fakes.py` pattern.
"""
from __future__ import annotations


class FakeInventoryRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, inventory_id):
        return self.by_id.get(inventory_id)

    def get_by_code(self, code):
        return next((i for i in self.by_id.values() if i.code.value == code), None)

    def get_by_product_variant(self, product_variant_id):
        return next((i for i in self.by_id.values() if i.product_variant_id == product_variant_id), None)

    def save(self, inventory):
        self.by_id[inventory.id] = inventory
        return inventory

    def code_exists(self, code, exclude_id=None) -> bool:
        return any(i.code.value == code and i.id != exclude_id for i in self.by_id.values())

    def list_for_admin(self, status, query, page, page_size):
        results = list(self.by_id.values())
        if status:
            results = [i for i in results if i.status.value == status]
        return results[(page - 1) * page_size : page * page_size], len(results)


class FakeWarehouseInventoryRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}
        self.ledger_entries: list = []

    def get_by_id(self, warehouse_inventory_id):
        return self.by_id.get(warehouse_inventory_id)

    def get_by_id_for_update(self, warehouse_inventory_id):
        return self.by_id.get(warehouse_inventory_id)

    def get_by_inventory_and_warehouse(self, inventory_id, warehouse_id):
        return next((wi for wi in self.by_id.values() if wi.inventory_id == inventory_id and wi.warehouse_id == warehouse_id), None)

    def save(self, warehouse_inventory):
        self.by_id[warehouse_inventory.id] = warehouse_inventory
        return warehouse_inventory

    def list_by_inventory(self, inventory_id):
        return [wi for wi in self.by_id.values() if wi.inventory_id == inventory_id]

    def list_by_warehouse(self, warehouse_id):
        return [wi for wi in self.by_id.values() if wi.warehouse_id == warehouse_id]

    def persist_transaction_and_ledger(self, warehouse_inventory_id, transaction_entity, ledger_entity) -> None:
        self.ledger_entries.append((warehouse_inventory_id, transaction_entity, ledger_entity))


class FakeBatchRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, batch_id):
        return self.by_id.get(batch_id)

    def get_by_number(self, batch_number):
        return next((b for b in self.by_id.values() if b.batch_number.value == batch_number), None)

    def save(self, batch):
        self.by_id[batch.id] = batch
        return batch

    def number_exists(self, batch_number, exclude_id=None) -> bool:
        return any(b.batch_number.value == batch_number and b.id != exclude_id for b in self.by_id.values())

    def list_candidates_for_allocation(self, inventory_id, warehouse_id, as_of):
        return []

    def list_by_inventory(self, inventory_id):
        return [b for b in self.by_id.values() if b.inventory_id == inventory_id]


class FakeSerialRepository:
    def __init__(self) -> None:
        self.numbers: set = set()

    def serial_exists(self, serial_number, exclude_batch_id=None) -> bool:
        return serial_number in self.numbers

    def get_batch_id_for_serial(self, serial_number):
        return None


class FakeReservationRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, reservation_id):
        return self.by_id.get(reservation_id)

    def get_by_number(self, reservation_number):
        return next((r for r in self.by_id.values() if r.reservation_number.value == reservation_number), None)

    def save(self, reservation):
        self.by_id[reservation.id] = reservation
        return reservation

    def list_expired(self, as_of):
        return [r for r in self.by_id.values() if r.expires_at and r.expires_at <= as_of]


class FakeCycleCountRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, cycle_count_id):
        return self.by_id.get(cycle_count_id)

    def save(self, cycle_count):
        self.by_id[cycle_count.id] = cycle_count
        return cycle_count


class FakePhysicalInventoryRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, physical_inventory_id):
        return self.by_id.get(physical_inventory_id)

    def save(self, physical_inventory):
        self.by_id[physical_inventory.id] = physical_inventory
        return physical_inventory


class FakeSnapshotRepository:
    def __init__(self) -> None:
        self.by_id: dict = {}

    def get_by_id(self, snapshot_id):
        return self.by_id.get(snapshot_id)

    def get_latest_version(self) -> int:
        if not self.by_id:
            return 0
        return max(s.version.value for s in self.by_id.values())

    def save(self, snapshot):
        self.by_id[snapshot.id] = snapshot
        return snapshot


class FakeLedgerRepository:
    def __init__(self) -> None:
        self.entries: list = []

    def list_entries(self, warehouse_inventory_id, stock_status=None):
        return [e for e in self.entries if e["warehouse_inventory_id"] == warehouse_inventory_id and (stock_status is None or e["stock_status"] == stock_status)]

    def get_latest_balance(self, warehouse_inventory_id, stock_status) -> int:
        matching = self.list_entries(warehouse_inventory_id, stock_status)
        return matching[-1]["balance_after"] if matching else 0


def collect_events(sink: list):
    def _stage(events: list[tuple[str, dict]]) -> None:
        sink.extend(events)

    return _stage
