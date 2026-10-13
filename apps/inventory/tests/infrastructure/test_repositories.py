"""
Repository integration tests -- require a real PostgreSQL database.
Matches every prior module's `tests/infrastructure/test_repositories.py`
pattern. Includes explicit database-constraint verification tests, not
just repository round-trip tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from django.db import IntegrityError

from apps.inventory.domain.aggregates import Batch, Inventory, WarehouseInventory
from apps.inventory.domain.value_objects import BatchNumber, InventoryCode, StockQuantity
from apps.inventory.infrastructure.repositories import DjangoBatchRepository, DjangoInventoryRepository, DjangoWarehouseInventoryRepository
from common.exceptions import ConflictError

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoInventoryRepository:
    def test_save_then_get_by_id_round_trips(self):
        repo = DjangoInventoryRepository()
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY101"), product_variant_id=uuid.uuid4())
        repo.save(inventory)

        fetched = repo.get_by_id(inventory.id)
        assert fetched is not None
        assert fetched.code.value == "WHEY101"

    def test_get_by_code(self):
        repo = DjangoInventoryRepository()
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY102"), product_variant_id=uuid.uuid4())
        repo.save(inventory)
        assert repo.get_by_code("WHEY102").id == inventory.id

    def test_database_level_unique_product_variant_constraint(self):
        """Verifies the unique constraint on product_variant_id actually prevents two inventory items for the same variant at the DB layer, not just the application-layer duplicate check."""
        repo = DjangoInventoryRepository()
        variant_id = uuid.uuid4()
        repo.save(Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY103"), product_variant_id=variant_id))
        with pytest.raises(ConflictError):
            repo.save(Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY104"), product_variant_id=variant_id))

    def test_code_exists_respects_exclusion(self):
        repo = DjangoInventoryRepository()
        inventory = Inventory(id=uuid.uuid4(), code=InventoryCode("WHEY105"), product_variant_id=uuid.uuid4())
        repo.save(inventory)
        assert repo.code_exists("WHEY105") is True
        assert repo.code_exists("WHEY105", exclude_id=inventory.id) is False


def _make_real_inventory_id() -> uuid.UUID:
    """A real, persisted InventoryModel row's id -- WarehouseInventory/Batch's own `inventory_id` is a real foreign key at the database level, so a bare uuid.uuid4() with no corresponding row genuinely violates it, matching test_database_level_negative_stock_constraint's own established pattern below."""
    from apps.inventory.infrastructure import models as orm
    return orm.InventoryModel.objects.create(code=f"TESTINV-{uuid.uuid4().hex[:8].upper()}", product_variant_id=uuid.uuid4()).id


class TestDjangoWarehouseInventoryRepository:
    def test_save_and_get_round_trips_all_buckets(self):
        repo = DjangoWarehouseInventoryRepository()
        wi = WarehouseInventory(id=uuid.uuid4(), inventory_id=_make_real_inventory_id(), warehouse_id=uuid.uuid4())
        wi.receive(StockQuantity(10), "PO-001", datetime.utcnow())
        repo.save(wi)

        fetched = repo.get_by_id(wi.id)
        from apps.inventory.domain.enums import StockStatus

        assert fetched.get_quantity(StockStatus.INCOMING) == 10

    def test_database_level_negative_stock_constraint(self):
        """Verifies the CheckConstraint on available_quantity actually rejects a negative value at the DB layer -- bypassing the domain aggregate entirely to prove this isn't only an application-level guard."""
        from apps.inventory.infrastructure import models as orm

        with pytest.raises(IntegrityError):
            orm.WarehouseInventoryModel.objects.create(inventory=orm.InventoryModel.objects.create(code="WHEY106", product_variant_id=uuid.uuid4()), warehouse_id=uuid.uuid4(), available_quantity=-1)

    def test_persist_transaction_and_ledger(self):
        from apps.inventory.infrastructure import models as orm

        repo = DjangoWarehouseInventoryRepository()
        wi = WarehouseInventory(id=uuid.uuid4(), inventory_id=_make_real_inventory_id(), warehouse_id=uuid.uuid4())
        repo.save(wi)
        transaction, ledger = wi.receive(StockQuantity(10), "PO-001", datetime.utcnow())
        repo.save(wi)
        repo.persist_transaction_and_ledger(wi.id, transaction, ledger)

        assert orm.InventoryTransactionModel.objects.filter(id=transaction.id).exists()
        assert orm.InventoryLedgerModel.objects.filter(id=ledger.id).exists()

    def test_get_by_inventory_and_warehouse(self):
        repo = DjangoWarehouseInventoryRepository()
        inventory_id, warehouse_id = _make_real_inventory_id(), uuid.uuid4()
        wi = WarehouseInventory(id=uuid.uuid4(), inventory_id=inventory_id, warehouse_id=warehouse_id)
        repo.save(wi)
        found = repo.get_by_inventory_and_warehouse(inventory_id, warehouse_id)
        assert found.id == wi.id


class TestDjangoBatchRepository:
    def test_database_level_unique_batch_number_constraint(self):
        from apps.inventory.infrastructure import models as orm

        inventory_row = orm.InventoryModel.objects.create(code="WHEY107", product_variant_id=uuid.uuid4())
        orm.BatchModel.objects.create(inventory=inventory_row, batch_number="BATCH-101")
        with pytest.raises(IntegrityError):
            orm.BatchModel.objects.create(inventory=inventory_row, batch_number="BATCH-101")

    def test_database_level_expiration_after_manufacture_constraint(self):
        from apps.inventory.infrastructure import models as orm

        inventory_row = orm.InventoryModel.objects.create(code="WHEY108", product_variant_id=uuid.uuid4())
        with pytest.raises(IntegrityError):
            orm.BatchModel.objects.create(inventory=inventory_row, batch_number="BATCH-102", manufacture_date="2026-06-01", expiration_date="2026-01-01")

    def test_save_and_get_batch_with_serials(self):
        repo = DjangoBatchRepository()
        batch = Batch(id=uuid.uuid4(), inventory_id=_make_real_inventory_id(), batch_number=BatchNumber("BATCH-103"))
        from apps.inventory.domain.entities import SerialItem
        from apps.inventory.domain.value_objects import SerialNumber

        batch.register_serial(SerialItem(id=uuid.uuid4(), serial_number=SerialNumber("SN00099999")))
        repo.save(batch)

        fetched = repo.get_by_id(batch.id)
        assert len(fetched.serials) == 1

    def test_number_exists_respects_exclusion(self):
        repo = DjangoBatchRepository()
        batch = Batch(id=uuid.uuid4(), inventory_id=_make_real_inventory_id(), batch_number=BatchNumber("BATCH-104"))
        repo.save(batch)
        assert repo.number_exists("BATCH-104") is True
        assert repo.number_exists("BATCH-104", exclude_id=batch.id) is False
