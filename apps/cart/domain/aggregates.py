"""
Cart aggregate root.

A single aggregate (`Cart`) rather than several, unlike most prior
modules -- Cart's own bounded-context brief is explicit that it "owns
shopping cart state only," and every capability in this phase's list
(guest/authenticated carts, saved carts, merge, snapshots, checkout
readiness) is a state or transition of one cart, not an independently
life-cycled thing of its own. `CartItem`/`CartSnapshot`/
`CartAuditEntry`/estimate references (entities.py) are all owned
directly by `Cart`, with no independent repository or identity outside
their owning cart.

Cross-module references (CartItem.product_variant_id ->
products.ProductVariant, PriceReference.price_snapshot_id ->
pricing.PriceSnapshot, InventoryReservationReference.reservation_id ->
inventory.Reservation, Cart.customer_id -> identity.User) are IDs
only, per this module's explicit "never domain imports" rule --
verified true by grep after this file was written, not just declared.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.cart.domain.entities import (
    CartAuditEntry, CartItem, CartSnapshot, InventoryReservationReference, PriceReference,
    ShippingEstimateReference, TaxEstimateReference,
)
from apps.cart.domain.enums import (
    CartItemStatus, CartLockReason, CartSource, CartStatus, CartType, CheckoutReadiness, MergeStrategy,
)
from apps.cart.domain.events import (
    CartArchivedEvent, CartCleared, CartCreated, CartExpiredEvent, CartLockedEvent, CartMerged, CartRestored,
    CartSaved, CartSnapshotCreated, CartSnapshotRestored, CartUnlocked, CheckoutReadinessCalculated,
    CouponReferenceApplied, CouponReferenceRemoved, CustomerAssigned, ItemAdded, ItemQuantityUpdated, ItemRemoved,
    PriceSnapshotAttached, PriceSnapshotDetached, ReservationAttached, ReservationDetached,
)
from apps.cart.domain.exceptions import (
    CartAlreadyConverted, CartAlreadyLocked, CartArchived, CartEntityNotFound, CartItemNotFound, CartLocked,
    CartNotLocked, CartOwnershipConflict, InvalidCartLifecycleTransition, InvalidQuantity,
)
from apps.cart.domain.value_objects import (
    CartCode, CartNote, CartToken, CartVersion, CurrencyCode, GiftMessage, MergeResult, Money, Quantity,
    RegionCode, ChannelCode, SnapshotToken,
)
from common.exceptions import ValidationFailed


@dataclass(slots=True)
class Cart:
    """Aggregate root -- the entire Cart bounded context is this one aggregate plus its owned entities."""

    id: uuid.UUID
    code: CartCode
    token: CartToken
    currency: CurrencyCode
    cart_type: CartType = CartType.GUEST
    source: CartSource = CartSource.WEB
    status: CartStatus = CartStatus.ACTIVE
    version: CartVersion = field(default_factory=lambda: CartVersion(1))
    region: RegionCode | None = None
    channel: ChannelCode | None = None
    customer_id: uuid.UUID | None = None
    items: dict[uuid.UUID, CartItem] = field(default_factory=dict)
    coupon_ids: set = field(default_factory=set)
    promotion_ids: set = field(default_factory=set)
    shipping_estimate: ShippingEstimateReference | None = None
    tax_estimate: TaxEstimateReference | None = None
    note: CartNote | None = None
    gift_message: GiftMessage | None = None
    expires_at: datetime | None = None
    lock_reason: CartLockReason | None = None
    snapshots: dict[uuid.UUID, CartSnapshot] = field(default_factory=dict)
    audit_log: list[CartAuditEntry] = field(default_factory=list)

    # --- Internal helpers ------------------------------------------------

    def _bump_version(self) -> None:
        self.version = self.version.next()

    def _audit(self, action: str, at: datetime, actor_id: uuid.UUID | None = None, **details) -> None:
        self.audit_log.append(CartAuditEntry(id=uuid.uuid4(), action=action, actor_id=actor_id, occurred_at=at, details=details))

    def _assert_mutable(self) -> None:
        if self.lock_reason is not None:
            raise CartLocked(f"This cart is locked ({self.lock_reason.value}) and cannot be modified.")
        if self.status == CartStatus.ARCHIVED:
            raise CartArchived("This cart is archived and cannot be modified.")
        if self.status == CartStatus.CONVERTED:
            raise CartAlreadyConverted("This cart has already been converted to an order and cannot be modified.")

    def _find_item_for_variant(self, product_variant_id: uuid.UUID) -> CartItem | None:
        return next((i for i in self.items.values() if i.product_variant_id == product_variant_id and i.status != CartItemStatus.REMOVED), None)

    # --- Item management -------------------------------------------------

    def add_item(self, product_variant_id: uuid.UUID, quantity: int, at: datetime, note: CartNote | None = None) -> ItemAdded:
        """Adding an already-present variant increases its quantity rather than creating a duplicate line -- 'Quantity Management' applies from the first add, not only on explicit updates."""
        self._assert_mutable()
        if quantity <= 0:
            raise InvalidQuantity("Quantity added must be positive.")

        existing = self._find_item_for_variant(product_variant_id)
        if existing is not None:
            existing.quantity = existing.quantity + Quantity(quantity)
            self._bump_version()
            self._audit("item_quantity_increased", at, product_variant_id=str(product_variant_id), added=quantity)
            return ItemAdded(cart_id=self.id, item_id=existing.id, product_variant_id=product_variant_id, quantity=existing.quantity.value)

        item = CartItem(id=uuid.uuid4(), product_variant_id=product_variant_id, quantity=Quantity(quantity), note=note, added_at=at)
        self.items[item.id] = item
        self._bump_version()
        self._audit("item_added", at, product_variant_id=str(product_variant_id), quantity=quantity)
        return ItemAdded(cart_id=self.id, item_id=item.id, product_variant_id=product_variant_id, quantity=quantity)

    def remove_item(self, item_id: uuid.UUID, at: datetime) -> ItemRemoved:
        self._assert_mutable()
        item = self.items.get(item_id)
        if item is None:
            raise CartItemNotFound(f"Cart item '{item_id}' not found.")
        item.status = CartItemStatus.REMOVED
        self._bump_version()
        self._audit("item_removed", at, item_id=str(item_id))
        return ItemRemoved(cart_id=self.id, item_id=item_id)

    def update_quantity(self, item_id: uuid.UUID, new_quantity: int, at: datetime) -> ItemQuantityUpdated:
        self._assert_mutable()
        item = self.items.get(item_id)
        if item is None:
            raise CartItemNotFound(f"Cart item '{item_id}' not found.")
        if new_quantity <= 0:
            raise InvalidQuantity("Quantity must be positive -- use remove_item() to remove a line entirely.")

        old_quantity = item.quantity.value
        item.quantity = Quantity(new_quantity)
        self._bump_version()
        self._audit("item_quantity_updated", at, item_id=str(item_id), old_quantity=old_quantity, new_quantity=new_quantity)
        return ItemQuantityUpdated(cart_id=self.id, item_id=item_id, old_quantity=old_quantity, new_quantity=new_quantity)

    def bulk_update_items(self, updates: dict, at: datetime) -> list[ItemQuantityUpdated]:
        """'Bulk Update' -- applies every update, collecting events; a single bad item_id fails the whole batch (all-or-nothing), since a partially-applied bulk update would leave the cart in a state the caller never actually requested."""
        for item_id in updates:
            if item_id not in self.items:
                raise CartItemNotFound(f"Cart item '{item_id}' not found.")
        return [self.update_quantity(item_id, quantity, at) for item_id, quantity in updates.items()]

    def clear(self, at: datetime) -> CartCleared:
        self._assert_mutable()
        active_items = [i for i in self.items.values() if i.status != CartItemStatus.REMOVED]
        for item in active_items:
            item.status = CartItemStatus.REMOVED
        self._bump_version()
        self._audit("cart_cleared", at, items_removed=len(active_items))
        return CartCleared(cart_id=self.id, items_removed=len(active_items))

    # --- Coupon / Promotion references -----------------------------------

    def apply_coupon_reference(self, coupon_id: uuid.UUID, at: datetime) -> CouponReferenceApplied:
        self._assert_mutable()
        self.coupon_ids.add(coupon_id)
        self._bump_version()
        self._audit("coupon_applied", at, coupon_id=str(coupon_id))
        return CouponReferenceApplied(cart_id=self.id, coupon_id=coupon_id)

    def remove_coupon_reference(self, coupon_id: uuid.UUID, at: datetime) -> CouponReferenceRemoved:
        self._assert_mutable()
        self.coupon_ids.discard(coupon_id)
        self._bump_version()
        self._audit("coupon_removed", at, coupon_id=str(coupon_id))
        return CouponReferenceRemoved(cart_id=self.id, coupon_id=coupon_id)

    # --- Price / Reservation references ------------------------------------

    def attach_price_snapshot(self, item_id: uuid.UUID, price_snapshot_id: uuid.UUID, unit_amount: Money, at: datetime) -> PriceSnapshotAttached:
        item = self.items.get(item_id)
        if item is None:
            raise CartItemNotFound(f"Cart item '{item_id}' not found.")
        item.price_reference = PriceReference(price_snapshot_id=price_snapshot_id, unit_amount=unit_amount, applied_at=at)
        if item.status == CartItemStatus.PRICE_CHANGED:
            item.status = CartItemStatus.ACTIVE
        self._bump_version()
        return PriceSnapshotAttached(cart_id=self.id, item_id=item_id, price_snapshot_id=price_snapshot_id)

    def detach_price_snapshot(self, item_id: uuid.UUID) -> PriceSnapshotDetached:
        item = self.items.get(item_id)
        if item is None:
            raise CartItemNotFound(f"Cart item '{item_id}' not found.")
        item.price_reference = None
        self._bump_version()
        return PriceSnapshotDetached(cart_id=self.id, item_id=item_id)

    def attach_reservation(self, item_id: uuid.UUID, reservation_id: uuid.UUID, at: datetime, expires_at: datetime | None = None) -> ReservationAttached:
        item = self.items.get(item_id)
        if item is None:
            raise CartItemNotFound(f"Cart item '{item_id}' not found.")
        item.reservation_reference = InventoryReservationReference(reservation_id=reservation_id, reserved_at=at, expires_at=expires_at)
        self._bump_version()
        return ReservationAttached(cart_id=self.id, item_id=item_id, reservation_id=reservation_id)

    def detach_reservation(self, item_id: uuid.UUID) -> ReservationDetached:
        item = self.items.get(item_id)
        if item is None:
            raise CartItemNotFound(f"Cart item '{item_id}' not found.")
        item.reservation_reference = None
        self._bump_version()
        return ReservationDetached(cart_id=self.id, item_id=item_id)

    def attach_shipping_estimate(self, estimate: ShippingEstimateReference) -> None:
        self.shipping_estimate = estimate
        self._bump_version()

    def attach_tax_estimate(self, estimate: TaxEstimateReference) -> None:
        self.tax_estimate = estimate
        self._bump_version()

    # --- Lifecycle -------------------------------------------------------

    def save(self) -> CartSaved:
        if self.status != CartStatus.ACTIVE:
            raise InvalidCartLifecycleTransition("Only an active cart can be saved.")
        self.status = CartStatus.SAVED
        return CartSaved(cart_id=self.id)

    def archive(self) -> CartArchivedEvent:
        if self.status == CartStatus.ARCHIVED:
            raise InvalidCartLifecycleTransition("This cart is already archived.")
        if self.status == CartStatus.CONVERTED:
            raise CartAlreadyConverted("A converted cart cannot be archived.")
        self.status = CartStatus.ARCHIVED
        return CartArchivedEvent(cart_id=self.id)

    def expire(self, at: datetime) -> CartExpiredEvent:
        if self.status not in (CartStatus.ACTIVE, CartStatus.SAVED):
            raise InvalidCartLifecycleTransition(f"Cannot expire a cart that is already {self.status.value}.")
        if self.expires_at is not None and at < self.expires_at:
            raise ValidationFailed("This cart has not yet reached its expiration time.")
        self.status = CartStatus.EXPIRED
        return CartExpiredEvent(cart_id=self.id)

    def restore(self) -> CartRestored:
        if self.status not in (CartStatus.EXPIRED, CartStatus.ARCHIVED):
            raise InvalidCartLifecycleTransition("Only an expired or archived cart can be restored.")
        self.status = CartStatus.ACTIVE
        return CartRestored(cart_id=self.id)

    def lock(self, reason: CartLockReason) -> CartLockedEvent:
        if self.lock_reason is not None:
            raise CartAlreadyLocked("This cart is already locked.")
        self.lock_reason = reason
        return CartLockedEvent(cart_id=self.id, reason=reason.value)

    def unlock(self) -> CartUnlocked:
        if self.lock_reason is None:
            raise CartNotLocked("This cart is not locked.")
        self.lock_reason = None
        return CartUnlocked(cart_id=self.id)

    # --- Ownership / Merge -------------------------------------------------

    def assign_customer(self, customer_id: uuid.UUID, at: datetime) -> CustomerAssigned:
        """Guest -> authenticated conversion -- an already-authenticated cart's ownership cannot be reassigned to a different customer."""
        if self.customer_id is not None and self.customer_id != customer_id:
            raise CartOwnershipConflict("This cart already belongs to a different customer.")
        self.customer_id = customer_id
        self.cart_type = CartType.AUTHENTICATED
        self._bump_version()
        self._audit("customer_assigned", at, customer_id=str(customer_id))
        return CustomerAssigned(cart_id=self.id, customer_id=customer_id)

    def merge_guest_cart(self, guest_cart: "Cart", strategy: MergeStrategy, at: datetime) -> tuple[MergeResult, CartMerged]:
        """Merges `guest_cart`'s active items into `self` (the authenticated cart) per `strategy`. `self` is mutated; `guest_cart` is left untouched (the caller archives it separately, since Cart doesn't delete other Cart instances from within one aggregate's own method)."""
        merged, replaced, skipped = 0, 0, 0
        guest_items = [i for i in guest_cart.items.values() if i.status != CartItemStatus.REMOVED]

        if strategy == MergeStrategy.REPLACE_WITH_GUEST:
            for item in list(self.items.values()):
                item.status = CartItemStatus.REMOVED
            for guest_item in guest_items:
                new_item = CartItem(id=uuid.uuid4(), product_variant_id=guest_item.product_variant_id, quantity=guest_item.quantity, note=guest_item.note, added_at=at)
                self.items[new_item.id] = new_item
                replaced += 1
        elif strategy == MergeStrategy.KEEP_AUTHENTICATED:
            for guest_item in guest_items:
                if self._find_item_for_variant(guest_item.product_variant_id) is None:
                    new_item = CartItem(id=uuid.uuid4(), product_variant_id=guest_item.product_variant_id, quantity=guest_item.quantity, note=guest_item.note, added_at=at)
                    self.items[new_item.id] = new_item
                    merged += 1
                else:
                    skipped += 1
        else:  # SUM_QUANTITIES
            for guest_item in guest_items:
                existing = self._find_item_for_variant(guest_item.product_variant_id)
                if existing is not None:
                    existing.quantity = existing.quantity + guest_item.quantity
                    merged += 1
                else:
                    new_item = CartItem(id=uuid.uuid4(), product_variant_id=guest_item.product_variant_id, quantity=guest_item.quantity, note=guest_item.note, added_at=at)
                    self.items[new_item.id] = new_item
                    merged += 1

        self._bump_version()
        self._audit("guest_cart_merged", at, source_cart_id=str(guest_cart.id), strategy=strategy.value)
        result = MergeResult(items_merged=merged, items_replaced=replaced, items_skipped=skipped, strategy_used=strategy.value)
        event = CartMerged(target_cart_id=self.id, source_cart_id=guest_cart.id, items_merged=merged + replaced, strategy=strategy.value)
        return result, event

    # --- Snapshots ---------------------------------------------------------

    def create_snapshot(self, at: datetime) -> tuple[CartSnapshot, CartSnapshotCreated]:
        active_items = [i for i in self.items.values() if i.status != CartItemStatus.REMOVED]
        items_snapshot = tuple(
            {
                "product_variant_id": str(i.product_variant_id), "quantity": i.quantity.value,
                "unit_amount": str(i.price_reference.unit_amount.amount) if i.price_reference else None,
            }
            for i in active_items
        )
        snapshot = CartSnapshot(id=uuid.uuid4(), token=SnapshotToken(uuid.uuid4()), version_at_capture=self.version.value, captured_at=at, items_snapshot=items_snapshot)
        self.snapshots[snapshot.id] = snapshot
        return snapshot, CartSnapshotCreated(cart_id=self.id, snapshot_id=snapshot.id)

    def restore_snapshot(self, snapshot_id: uuid.UUID, at: datetime) -> CartSnapshotRestored:
        """Restoring replaces current items with the snapshot's frozen quantities -- prices/reservations are NOT restored (a snapshot's frozen unit_amount is historical record only; re-attaching a live price snapshot is the caller's job, since only the caller can obtain a currently-valid one)."""
        self._assert_mutable()
        snapshot = self.snapshots.get(snapshot_id)
        if snapshot is None:
            raise CartEntityNotFound(f"Cart snapshot '{snapshot_id}' not found.")

        for item in list(self.items.values()):
            item.status = CartItemStatus.REMOVED

        for entry in snapshot.items_snapshot:
            new_item = CartItem(id=uuid.uuid4(), product_variant_id=uuid.UUID(entry["product_variant_id"]), quantity=Quantity(entry["quantity"]), added_at=at)
            self.items[new_item.id] = new_item

        self._bump_version()
        self._audit("snapshot_restored", at, snapshot_id=str(snapshot_id))
        return CartSnapshotRestored(cart_id=self.id, snapshot_id=snapshot_id)

    # --- Checkout readiness (structural check only -- see domain/services.py::CheckoutReadinessPolicy for the fuller, input-driven policy) ---

    def structural_checkout_readiness(self) -> CheckoutReadiness:
        active_items = [i for i in self.items.values() if i.status != CartItemStatus.REMOVED]
        if not active_items:
            return CheckoutReadiness.NOT_READY
        if self.lock_reason is not None or self.status != CartStatus.ACTIVE:
            return CheckoutReadiness.BLOCKED
        if any(i.price_reference is None for i in active_items):
            return CheckoutReadiness.NOT_READY
        if any(i.status in (CartItemStatus.OUT_OF_STOCK, CartItemStatus.INVALID) for i in active_items):
            return CheckoutReadiness.BLOCKED
        return CheckoutReadiness.READY
