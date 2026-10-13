from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from apps.inventory.domain.enums import InventoryHealthStatus
from apps.inventory.domain.exceptions import DuplicateBatch, DuplicateSerial, LedgerCorrupted
from apps.inventory.domain.services import (
    AdjustmentPolicy,
    BatchCandidate,
    BatchPolicy,
    ExpirationPolicy,
    FEFOAllocationPolicy,
    FIFOAllocationPolicy,
    InventoryHealthPolicy,
    LedgerPolicy,
    MovementPolicy,
    ReservationPolicy,
    SerialPolicy,
    SnapshotPolicy,
    ThresholdPolicy,
)
from apps.inventory.domain.value_objects import StockThreshold
from common.exceptions import ConflictError, ValidationFailed

pytestmark = pytest.mark.unit


def _candidate(days_old: int = 0, expires_in_days: int | None = None, available: int = 10) -> BatchCandidate:
    return BatchCandidate(
        batch_id=uuid.uuid4(), available_quantity=available, received_at=datetime.utcnow() - timedelta(days=days_old),
        expiration_date=date.today() + timedelta(days=expires_in_days) if expires_in_days is not None else None,
    )


class TestFIFOAllocationPolicy:
    def test_allocates_from_oldest_first(self):
        old = _candidate(days_old=10, available=5)
        new = _candidate(days_old=1, available=5)
        result = FIFOAllocationPolicy.allocate(7, [new, old])
        assert result.lines[0].batch_id == old.batch_id
        assert result.fully_allocated is True

    def test_partial_allocation_reports_unallocated(self):
        candidate = _candidate(available=5)
        result = FIFOAllocationPolicy.allocate(10, [candidate])
        assert result.fully_allocated is False
        assert result.unallocated_quantity == 5

    def test_splits_across_multiple_batches(self):
        a = _candidate(days_old=5, available=3)
        b = _candidate(days_old=3, available=3)
        result = FIFOAllocationPolicy.allocate(5, [a, b])
        assert len(result.lines) == 2
        assert result.fully_allocated is True


class TestFEFOAllocationPolicy:
    def test_allocates_from_soonest_expiring_first(self):
        far = _candidate(expires_in_days=100, available=5)
        near = _candidate(expires_in_days=5, available=5)
        result = FEFOAllocationPolicy.allocate(3, [far, near])
        assert result.lines[0].batch_id == near.batch_id

    def test_null_expiration_sorted_last(self):
        no_expiry = _candidate(expires_in_days=None, available=5)
        with_expiry = _candidate(expires_in_days=10, available=5)
        result = FEFOAllocationPolicy.allocate(8, [no_expiry, with_expiry])
        assert result.lines[0].batch_id == with_expiry.batch_id


class TestReservationPolicy:
    def test_sufficient_available_passes(self):
        ReservationPolicy.assert_sufficient_available(5, 10)

    def test_insufficient_available_raises(self):
        from apps.inventory.domain.exceptions import InsufficientStock

        with pytest.raises(InsufficientStock):
            ReservationPolicy.assert_sufficient_available(15, 10)

    def test_default_expiry_minutes(self):
        assert ReservationPolicy.default_expiry_minutes() == 30


class TestMovementPolicy:
    def test_distinct_endpoints_passes(self):
        MovementPolicy.assert_transfer_has_distinct_endpoints(uuid.uuid4(), uuid.uuid4())

    def test_identical_endpoints_raises(self):
        from apps.inventory.domain.exceptions import InvalidMovement

        wid = uuid.uuid4()
        with pytest.raises(InvalidMovement):
            MovementPolicy.assert_transfer_has_distinct_endpoints(wid, wid)


class TestAdjustmentPolicy:
    def test_damage_with_negative_delta_passes(self):
        AdjustmentPolicy.assert_reason_is_justified("damage", -5)

    def test_damage_with_positive_delta_raises(self):
        with pytest.raises(ValidationFailed):
            AdjustmentPolicy.assert_reason_is_justified("damage", 5)

    def test_found_with_positive_delta_passes(self):
        AdjustmentPolicy.assert_reason_is_justified("found", 5)

    def test_found_with_negative_delta_raises(self):
        with pytest.raises(ValidationFailed):
            AdjustmentPolicy.assert_reason_is_justified("found", -5)


class TestExpirationPolicy:
    def test_is_expired_true(self):
        assert ExpirationPolicy.is_expired(date(2026, 1, 1), date(2026, 1, 1)) is True

    def test_is_expired_none_date_is_false(self):
        assert ExpirationPolicy.is_expired(None, date(2026, 1, 1)) is False

    def test_days_until_expiration(self):
        assert ExpirationPolicy.days_until_expiration(date(2026, 1, 10), date(2026, 1, 1)) == 9

    def test_days_until_expiration_none(self):
        assert ExpirationPolicy.days_until_expiration(None, date(2026, 1, 1)) is None


class TestBatchAndSerialPolicy:
    def test_batch_unique_number_passes(self):
        BatchPolicy.assert_unique_number("BATCH-1", frozenset({"BATCH-2"}))

    def test_batch_duplicate_raises(self):
        with pytest.raises(DuplicateBatch):
            BatchPolicy.assert_unique_number("BATCH-1", frozenset({"BATCH-1"}))

    def test_serial_unique_number_passes(self):
        SerialPolicy.assert_unique_number("SN-1", frozenset({"SN-2"}))

    def test_serial_duplicate_raises(self):
        with pytest.raises(DuplicateSerial):
            SerialPolicy.assert_unique_number("SN-1", frozenset({"SN-1"}))


class TestInventoryHealthPolicy:
    def test_out_of_stock(self):
        assert InventoryHealthPolicy.evaluate(0, None) == InventoryHealthStatus.OUT_OF_STOCK

    def test_healthy_without_threshold(self):
        assert InventoryHealthPolicy.evaluate(100, None) == InventoryHealthStatus.HEALTHY

    def test_low_stock(self):
        threshold = StockThreshold(low_stock_at=10, reorder_at=5)
        assert InventoryHealthPolicy.evaluate(8, threshold) == InventoryHealthStatus.LOW_STOCK

    def test_overstocked(self):
        threshold = StockThreshold(low_stock_at=10, reorder_at=5, overstock_at=100)
        assert InventoryHealthPolicy.evaluate(150, threshold) == InventoryHealthStatus.OVERSTOCKED

    def test_needs_reorder(self):
        threshold = StockThreshold(low_stock_at=10, reorder_at=5)
        assert InventoryHealthPolicy.needs_reorder(4, threshold) is True
        assert InventoryHealthPolicy.needs_reorder(6, threshold) is False


class TestSnapshotPolicy:
    def test_monotonic_version_passes(self):
        SnapshotPolicy.assert_monotonic_version(2, 1)

    def test_non_monotonic_version_raises(self):
        with pytest.raises(ConflictError):
            SnapshotPolicy.assert_monotonic_version(1, 1)


class TestThresholdPolicy:
    def test_assert_valid_returns_threshold(self):
        threshold = ThresholdPolicy.assert_valid(10, 5, 100)
        assert threshold.low_stock_at == 10


class TestLedgerPolicy:
    def test_verify_balance_true(self):
        assert LedgerPolicy.verify_balance([10, -3, 5], 12) is True

    def test_verify_balance_false(self):
        assert LedgerPolicy.verify_balance([10, -3, 5], 99) is False

    def test_assert_balanced_passes(self):
        LedgerPolicy.assert_balanced([10, -3, 5], 12)

    def test_assert_balanced_raises_on_corruption(self):
        with pytest.raises(LedgerCorrupted):
            LedgerPolicy.assert_balanced([10, -3, 5], 99)
