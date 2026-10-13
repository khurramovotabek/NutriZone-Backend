"""
Inventory domain exceptions -- named to match this phase's brief
exactly, matching the pattern established across every prior module.
"""
from __future__ import annotations

from common.exceptions import BusinessRuleViolation, ConflictError, ValidationFailed


class NegativeStock(ValidationFailed):
    code = "NEGATIVE_STOCK"


class InsufficientStock(BusinessRuleViolation):
    code = "INSUFFICIENT_STOCK"


class DuplicateBatch(ConflictError):
    code = "DUPLICATE_BATCH"


class DuplicateSerial(ConflictError):
    code = "DUPLICATE_SERIAL"


class ReservationExpired(BusinessRuleViolation):
    code = "RESERVATION_EXPIRED"


class ReservationConflict(ConflictError):
    code = "RESERVATION_CONFLICT"


class InvalidMovement(BusinessRuleViolation):
    code = "INVALID_MOVEMENT"


class InvalidWarehouse(ValidationFailed):
    code = "INVALID_WAREHOUSE"


class InvalidShelf(ValidationFailed):
    code = "INVALID_SHELF"


class BatchExpired(BusinessRuleViolation):
    code = "BATCH_EXPIRED"


class InventoryArchived(ConflictError):
    code = "INVENTORY_ARCHIVED"


class LedgerCorrupted(BusinessRuleViolation):
    """Raised when replaying ledger entries does not reconcile with the current recorded balance -- see domain/services.py::LedgerPolicy."""

    code = "LEDGER_CORRUPTED"


class InventoryMismatch(BusinessRuleViolation):
    """Raised when a Cycle Count / Physical Inventory's counted quantity disagrees with the recorded quantity beyond an acceptable tolerance."""

    code = "INVENTORY_MISMATCH"


class InvalidInventoryLifecycleTransition(ConflictError):
    code = "INVALID_INVENTORY_LIFECYCLE_TRANSITION"


class InvalidReservationLifecycleTransition(ConflictError):
    code = "INVALID_RESERVATION_LIFECYCLE_TRANSITION"


class InvalidCycleCountLifecycleTransition(ConflictError):
    code = "INVALID_CYCLE_COUNT_LIFECYCLE_TRANSITION"


class InvalidPhysicalInventoryLifecycleTransition(ConflictError):
    code = "INVALID_PHYSICAL_INVENTORY_LIFECYCLE_TRANSITION"


class DamagedStockCannotBeReserved(BusinessRuleViolation):
    code = "DAMAGED_STOCK_CANNOT_BE_RESERVED"


class QuarantineStockCannotBeTransferred(BusinessRuleViolation):
    code = "QUARANTINE_STOCK_CANNOT_BE_TRANSFERRED"


class IncomingStockCannotBeSold(BusinessRuleViolation):
    code = "INCOMING_STOCK_CANNOT_BE_SOLD"


class ExpiredStockCannotBecomeAvailable(BusinessRuleViolation):
    code = "EXPIRED_STOCK_CANNOT_BECOME_AVAILABLE"


class InventoryEntityNotFound(ValidationFailed):
    code = "INVENTORY_ENTITY_NOT_FOUND"
