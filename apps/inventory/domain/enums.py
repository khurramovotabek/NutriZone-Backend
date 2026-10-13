"""
Inventory domain enums.

`inventory` IS one of the Domain Architecture Specification's original
eighteen bounded contexts -- no reconciliation note is needed here,
matching `store` and unlike `geo`.
"""
from __future__ import annotations

from common.utils import DomainStrEnum


class InventoryStatus(DomainStrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class StockStatus(DomainStrEnum):
    """The seven stock 'buckets' every quantity in this module lives in exactly one of at a time."""

    AVAILABLE = "available"
    RESERVED = "reserved"
    INCOMING = "incoming"
    DAMAGED = "damaged"
    EXPIRED = "expired"
    QUARANTINE = "quarantine"
    RETURNED = "returned"


class MovementType(DomainStrEnum):
    RECEIVE = "receive"
    TRANSFER = "transfer"
    RESERVE = "reserve"
    RELEASE = "release"
    SALE = "sale"
    RETURN = "return"
    DAMAGE = "damage"
    EXPIRE = "expire"
    ADJUSTMENT = "adjustment"


class AdjustmentReason(DomainStrEnum):
    STOCK_CORRECTION = "stock_correction"
    DAMAGE = "damage"
    LOSS = "loss"
    FOUND = "found"
    MANUAL = "manual"


class ReservationStatus(DomainStrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    RELEASED = "released"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class BatchStatus(DomainStrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    QUARANTINE = "quarantine"
    DEPLETED = "depleted"
    RECALLED = "recalled"


class SerialStatus(DomainStrEnum):
    IN_STOCK = "in_stock"
    RESERVED = "reserved"
    SOLD = "sold"
    DAMAGED = "damaged"
    RETURNED = "returned"
    DEACTIVATED = "deactivated"


class LedgerEntryType(DomainStrEnum):
    """Mirrors MovementType 1:1 -- every ledger entry records the movement that produced it, plus the resulting balance (see domain/entities.py::InventoryLedger)."""

    RECEIVE = "receive"
    TRANSFER = "transfer"
    RESERVE = "reserve"
    RELEASE = "release"
    SALE = "sale"
    RETURN = "return"
    DAMAGE = "damage"
    EXPIRE = "expire"
    ADJUSTMENT = "adjustment"


class InventorySnapshotStatus(DomainStrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class CycleCountStatus(DomainStrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PhysicalInventoryStatus(DomainStrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InventoryHealthStatus(DomainStrEnum):
    """Computed, not stored -- see domain/services.py::InventoryHealthPolicy."""

    HEALTHY = "healthy"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    OVERSTOCKED = "overstocked"
