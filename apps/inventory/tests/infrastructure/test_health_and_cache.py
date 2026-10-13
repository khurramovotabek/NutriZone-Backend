from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from apps.inventory.infrastructure.event_handlers import (
    CACHE_GROUPS,
    handle_inventory_event,
    invalidate_inventory_cache_group,
)
from apps.inventory.infrastructure.health import (
    check_inventory_batch,
    check_inventory_cache,
    check_inventory_ledger,
    check_inventory_repository,
    check_inventory_reservation,
    check_inventory_snapshot,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestHealthChecks:
    def test_check_inventory_repository_healthy(self):
        ok, detail = check_inventory_repository()
        assert ok is True

    def test_check_inventory_cache_round_trips(self):
        ok, detail = check_inventory_cache()
        assert ok is True

    def test_check_inventory_ledger_no_entries_is_ok(self):
        ok, detail = check_inventory_ledger()
        assert ok is True

    def test_check_inventory_ledger_detects_corruption(self):
        """Seeds a deliberately corrupted ledger entry and verifies the health check catches it -- not just that the check runs without error."""
        from apps.inventory.infrastructure import models as orm

        inventory_row = orm.InventoryModel.objects.create(code="WHEY201", product_variant_id=uuid.uuid4())
        wi_row = orm.WarehouseInventoryModel.objects.create(inventory=inventory_row, warehouse_id=uuid.uuid4(), available_quantity=10)
        orm.InventoryLedgerModel.objects.create(
            warehouse_inventory=wi_row, entry_type="receive", stock_status="available", quantity_delta=10, balance_after=999, reference="PO-CORRUPT", occurred_at=datetime.utcnow(),
        )

        ok, detail = check_inventory_ledger()
        assert ok is False
        assert "reconcile" in detail

    def test_check_inventory_snapshot_reports_pending_count(self):
        ok, detail = check_inventory_snapshot()
        assert ok is True
        assert "pending" in detail

    def test_check_inventory_batch_flags_overdue_expired(self):
        from apps.inventory.infrastructure import models as orm

        inventory_row = orm.InventoryModel.objects.create(code="WHEY202", product_variant_id=uuid.uuid4())
        orm.BatchModel.objects.create(inventory=inventory_row, batch_number="BATCH-201", status="active", expiration_date="2020-01-01")

        ok, detail = check_inventory_batch()
        assert ok is False
        assert "expiration" in detail

    def test_check_inventory_reservation_healthy_when_few_overdue(self):
        ok, detail = check_inventory_reservation()
        assert ok is True


class TestCacheGroupInvalidation:
    def test_rejects_unknown_group(self):
        with pytest.raises(ValueError):
            invalidate_inventory_cache_group("not_a_real_group")

    def test_all_eight_cache_groups_present(self):
        assert len(CACHE_GROUPS) == 8

    def test_invalidate_group_does_not_raise(self):
        invalidate_inventory_cache_group("inventory_detail")


class TestEventHandlerDispatch:
    def test_handle_inventory_created_does_not_raise(self):
        handle_inventory_event("InventoryCreated", {"inventory_id": "x"})

    def test_handle_event_with_no_cache_side_effect_does_not_raise(self):
        """CycleCountStarted has an empty cache-group tuple -- verifies dispatch handles that correctly rather than erroring."""
        handle_inventory_event("CycleCountStarted", {})

    def test_handle_unknown_event_is_a_noop(self):
        handle_inventory_event("SomeUnregisteredEvent", {})
