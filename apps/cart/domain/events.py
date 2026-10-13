"""
Cart domain events.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class CartCreated:
    cart_id: uuid.UUID
    cart_type: str
    source: str

    def to_payload(self) -> dict:
        return {**asdict(self), "cart_id": str(self.cart_id)}


@dataclass(frozen=True, slots=True)
class ItemAdded:
    cart_id: uuid.UUID
    item_id: uuid.UUID
    product_variant_id: uuid.UUID
    quantity: int

    def to_payload(self) -> dict:
        return {**asdict(self), "cart_id": str(self.cart_id), "item_id": str(self.item_id), "product_variant_id": str(self.product_variant_id)}


@dataclass(frozen=True, slots=True)
class ItemRemoved:
    cart_id: uuid.UUID
    item_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cart_id": str(self.cart_id), "item_id": str(self.item_id)}


@dataclass(frozen=True, slots=True)
class ItemQuantityUpdated:
    cart_id: uuid.UUID
    item_id: uuid.UUID
    old_quantity: int
    new_quantity: int

    def to_payload(self) -> dict:
        return {**asdict(self), "cart_id": str(self.cart_id), "item_id": str(self.item_id)}


@dataclass(frozen=True, slots=True)
class CartCleared:
    cart_id: uuid.UUID
    items_removed: int

    def to_payload(self) -> dict:
        return {**asdict(self), "cart_id": str(self.cart_id)}


@dataclass(frozen=True, slots=True)
class CartMerged:
    target_cart_id: uuid.UUID
    source_cart_id: uuid.UUID
    items_merged: int
    strategy: str

    def to_payload(self) -> dict:
        return {**asdict(self), "target_cart_id": str(self.target_cart_id), "source_cart_id": str(self.source_cart_id)}


@dataclass(frozen=True, slots=True)
class CustomerAssigned:
    cart_id: uuid.UUID
    customer_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cart_id": str(self.cart_id), "customer_id": str(self.customer_id)}


@dataclass(frozen=True, slots=True)
class CouponReferenceApplied:
    cart_id: uuid.UUID
    coupon_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cart_id": str(self.cart_id), "coupon_id": str(self.coupon_id)}


@dataclass(frozen=True, slots=True)
class CouponReferenceRemoved:
    cart_id: uuid.UUID
    coupon_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cart_id": str(self.cart_id), "coupon_id": str(self.coupon_id)}


@dataclass(frozen=True, slots=True)
class PriceSnapshotAttached:
    cart_id: uuid.UUID
    item_id: uuid.UUID
    price_snapshot_id: uuid.UUID

    def to_payload(self) -> dict:
        return {**asdict(self), "cart_id": str(self.cart_id), "item_id": str(self.item_id), "price_snapshot_id": str(self.price_snapshot_id)}


@dataclass(frozen=True, slots=True)
class PriceSnapshotDetached:
    cart_id: uuid.UUID
    item_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cart_id": str(self.cart_id), "item_id": str(self.item_id)}


@dataclass(frozen=True, slots=True)
class ReservationAttached:
    cart_id: uuid.UUID
    item_id: uuid.UUID
    reservation_id: uuid.UUID

    def to_payload(self) -> dict:
        return {**asdict(self), "cart_id": str(self.cart_id), "item_id": str(self.item_id), "reservation_id": str(self.reservation_id)}


@dataclass(frozen=True, slots=True)
class ReservationDetached:
    cart_id: uuid.UUID
    item_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cart_id": str(self.cart_id), "item_id": str(self.item_id)}


@dataclass(frozen=True, slots=True)
class CartSaved:
    cart_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cart_id": str(self.cart_id)}


@dataclass(frozen=True, slots=True)
class CartArchivedEvent:
    cart_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cart_id": str(self.cart_id)}


@dataclass(frozen=True, slots=True)
class CartExpiredEvent:
    cart_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cart_id": str(self.cart_id)}


@dataclass(frozen=True, slots=True)
class CartRestored:
    cart_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cart_id": str(self.cart_id)}


@dataclass(frozen=True, slots=True)
class CartLockedEvent:
    """Named with an Event suffix specifically to avoid colliding with the domain exception `CartLocked` (exceptions.py) -- the same naming-collision pattern already resolved identically for `apps.inventory`'s `InventoryArchivedEvent`/`InventoryArchived` and `apps.pricing`'s `PriceListArchivedEvent`/`PriceListArchived`. Caught here before it ever compiled as a real collision, not after."""

    cart_id: uuid.UUID
    reason: str

    def to_payload(self) -> dict:
        return {**asdict(self), "cart_id": str(self.cart_id)}


@dataclass(frozen=True, slots=True)
class CartUnlocked:
    cart_id: uuid.UUID

    def to_payload(self) -> dict:
        return {"cart_id": str(self.cart_id)}


@dataclass(frozen=True, slots=True)
class CartSnapshotCreated:
    cart_id: uuid.UUID
    snapshot_id: uuid.UUID

    def to_payload(self) -> dict:
        return {**asdict(self), "cart_id": str(self.cart_id), "snapshot_id": str(self.snapshot_id)}


@dataclass(frozen=True, slots=True)
class CartSnapshotRestored:
    cart_id: uuid.UUID
    snapshot_id: uuid.UUID

    def to_payload(self) -> dict:
        return {**asdict(self), "cart_id": str(self.cart_id), "snapshot_id": str(self.snapshot_id)}


@dataclass(frozen=True, slots=True)
class CheckoutReadinessCalculated:
    cart_id: uuid.UUID
    readiness: str

    def to_payload(self) -> dict:
        return {**asdict(self), "cart_id": str(self.cart_id)}
