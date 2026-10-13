"""
Inventory domain services.

Pure business rules with no I/O, per MIC §4 -- handed data by the
calling Application Service (e.g. a list of candidate batches sourced
from a repository query), never fetching it themselves. Matches every
prior module's domain/services.py pattern.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from apps.inventory.domain.enums import InventoryHealthStatus
from apps.inventory.domain.exceptions import InsufficientStock
from apps.inventory.domain.value_objects import StockThreshold


@dataclass(frozen=True, slots=True)
class BatchCandidate:
    """The minimal shape FIFO/FEFO allocation needs from a batch -- deliberately not the full `Batch` aggregate, so these policies stay pure and testable without constructing entire aggregates."""

    batch_id: object  # uuid.UUID
    available_quantity: int
    received_at: datetime
    expiration_date: date | None


@dataclass(frozen=True, slots=True)
class AllocationLine:
    batch_id: object
    quantity: int


@dataclass(frozen=True, slots=True)
class AllocationResult:
    lines: tuple[AllocationLine, ...]
    fully_allocated: bool
    unallocated_quantity: int


class FIFOAllocationPolicy:
    """First-In-First-Out: allocate from the oldest-received batch first -- used when expiration is not the primary concern (e.g. non-perishable goods)."""

    @staticmethod
    def allocate(requested_quantity: int, candidates: list[BatchCandidate]) -> AllocationResult:
        ordered = sorted(candidates, key=lambda c: c.received_at)
        return _greedy_allocate(requested_quantity, ordered)


class FEFOAllocationPolicy:
    """First-Expired-First-Out: allocate from the soonest-to-expire batch first -- the default for perishable/dated goods (matches this module's explicit "FEFO allocation" business rule)."""

    @staticmethod
    def allocate(requested_quantity: int, candidates: list[BatchCandidate]) -> AllocationResult:
        # Batches with no expiration date are treated as "never expiring" -- sorted last.
        ordered = sorted(candidates, key=lambda c: (c.expiration_date is None, c.expiration_date or date.max))
        return _greedy_allocate(requested_quantity, ordered)


def _greedy_allocate(requested_quantity: int, ordered_candidates: list[BatchCandidate]) -> AllocationResult:
    remaining = requested_quantity
    lines: list[AllocationLine] = []
    for candidate in ordered_candidates:
        if remaining <= 0:
            break
        take = min(remaining, candidate.available_quantity)
        if take > 0:
            lines.append(AllocationLine(batch_id=candidate.batch_id, quantity=take))
            remaining -= take
    return AllocationResult(lines=tuple(lines), fully_allocated=remaining == 0, unallocated_quantity=remaining)


class ReservationPolicy:
    @staticmethod
    def assert_sufficient_available(requested_quantity: int, available_quantity: int) -> None:
        if requested_quantity > available_quantity:
            raise InsufficientStock(f"Cannot reserve {requested_quantity} units; only {available_quantity} available.")

    @staticmethod
    def default_expiry_minutes() -> int:
        """The platform-standard reservation hold window -- centralized here so every caller (checkout reservation, admin manual hold) uses the same default rather than each hardcoding its own."""
        return 30


class MovementPolicy:
    @staticmethod
    def assert_transfer_has_distinct_endpoints(source_id, destination_id) -> None:
        from apps.inventory.domain.exceptions import InvalidMovement

        if source_id == destination_id:
            raise InvalidMovement("A transfer's source and destination must be different warehouse inventories.")


class AdjustmentPolicy:
    @staticmethod
    def assert_reason_is_justified(reason_value: str, quantity_delta: int) -> None:
        """A structural sanity check: DAMAGE/LOSS reasons should only ever decrease stock, FOUND should only ever increase it -- catches an obviously mis-recorded adjustment before it corrupts the ledger."""
        from common.exceptions import ValidationFailed

        if reason_value in ("damage", "loss") and quantity_delta > 0:
            raise ValidationFailed(f"Adjustment reason '{reason_value}' must have a negative quantity delta.")
        if reason_value == "found" and quantity_delta < 0:
            raise ValidationFailed("Adjustment reason 'found' must have a positive quantity delta.")


class ExpirationPolicy:
    @staticmethod
    def is_expired(expiration_date: date | None, as_of: date) -> bool:
        return expiration_date is not None and as_of >= expiration_date

    @staticmethod
    def days_until_expiration(expiration_date: date | None, as_of: date) -> int | None:
        if expiration_date is None:
            return None
        return (expiration_date - as_of).days


class BatchPolicy:
    @staticmethod
    def assert_unique_number(candidate_number: str, existing_numbers: frozenset[str]) -> None:
        from apps.inventory.domain.exceptions import DuplicateBatch

        if candidate_number in existing_numbers:
            raise DuplicateBatch(f"Batch number '{candidate_number}' already exists.")


class SerialPolicy:
    @staticmethod
    def assert_unique_number(candidate_number: str, existing_numbers: frozenset[str]) -> None:
        from apps.inventory.domain.exceptions import DuplicateSerial

        if candidate_number in existing_numbers:
            raise DuplicateSerial(f"Serial number '{candidate_number}' already exists.")


class InventoryHealthPolicy:
    """Computes the read-only `InventoryHealthStatus` (domain/enums.py) from current available quantity and configured thresholds -- a pure derivation, never stored."""

    @staticmethod
    def evaluate(available_quantity: int, threshold: StockThreshold | None) -> InventoryHealthStatus:
        if available_quantity <= 0:
            return InventoryHealthStatus.OUT_OF_STOCK
        if threshold is None:
            return InventoryHealthStatus.HEALTHY
        if threshold.overstock_at is not None and available_quantity >= threshold.overstock_at:
            return InventoryHealthStatus.OVERSTOCKED
        if available_quantity <= threshold.low_stock_at:
            return InventoryHealthStatus.LOW_STOCK
        return InventoryHealthStatus.HEALTHY

    @staticmethod
    def needs_reorder(available_quantity: int, threshold: StockThreshold | None) -> bool:
        return threshold is not None and available_quantity <= threshold.reorder_at


class SnapshotPolicy:
    @staticmethod
    def assert_monotonic_version(new_version: int, latest_existing_version: int) -> None:
        from common.exceptions import ConflictError

        if new_version <= latest_existing_version:
            raise ConflictError(f"Snapshot version {new_version} must be greater than the latest existing version {latest_existing_version}.")


class ThresholdPolicy:
    @staticmethod
    def assert_valid(low_stock_at: int, reorder_at: int, overstock_at: int | None) -> StockThreshold:
        return StockThreshold(low_stock_at=low_stock_at, reorder_at=reorder_at, overstock_at=overstock_at)


class LedgerPolicy:
    """
    'Ledger balancing': replaying every `InventoryLedger` entry's
    `quantity_delta` for a given (warehouse_inventory, stock_status)
    pair, starting from zero, must equal the most recent entry's
    `balance_after`. Handed the already-queried entry list by the
    Application Service (a repository concern) -- this stays a pure
    function of that list.
    """

    @staticmethod
    def verify_balance(quantity_deltas_in_order: list[int], claimed_final_balance: int) -> bool:
        return sum(quantity_deltas_in_order) == claimed_final_balance

    @staticmethod
    def assert_balanced(quantity_deltas_in_order: list[int], claimed_final_balance: int) -> None:
        from apps.inventory.domain.exceptions import LedgerCorrupted

        if not LedgerPolicy.verify_balance(quantity_deltas_in_order, claimed_final_balance):
            replayed = sum(quantity_deltas_in_order)
            raise LedgerCorrupted(f"Ledger replay produced balance {replayed}, but the recorded balance is {claimed_final_balance}.")
