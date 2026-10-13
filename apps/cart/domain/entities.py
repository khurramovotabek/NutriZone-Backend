"""
Cart domain entities (non-root members of the Cart aggregate).

Every cross-module reference here (product_variant_id,
price_snapshot_id, reservation_id, shipping_estimate_id,
tax_estimate_id) is a plain `uuid.UUID` field -- never a type imported
from Products/Pricing/Inventory/a future Fulfillment module. This is
the concrete mechanism behind this module's "Cart NEVER imports
Ordering/Pricing/Inventory/Wallet/Loyalty/Fulfillment domain" rule.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.cart.domain.enums import CartItemStatus, CartValidationIssueCode, CartValidationSeverity
from apps.cart.domain.value_objects import CartNote, EstimatedAmount, Money, Quantity, SnapshotToken


@dataclass(slots=True)
class PriceReference:
    """Non-root value holder, carried by CartItem -- 'Applied Price Snapshot': the specific Pricing snapshot this line item's price was locked against, plus the actual unit amount at that moment (so Cart can display/total a price without ever calling back into Pricing)."""

    price_snapshot_id: uuid.UUID
    unit_amount: Money
    applied_at: datetime


@dataclass(slots=True)
class InventoryReservationReference:
    """Non-root value holder, carried by CartItem -- 'Inventory Reservation Reference': the specific Inventory reservation backing this line item's stock hold."""

    reservation_id: uuid.UUID
    reserved_at: datetime
    expires_at: datetime | None = None


@dataclass(slots=True)
class CartItem:
    """Non-root entity, owned by Cart -- one product variant line item."""

    id: uuid.UUID
    product_variant_id: uuid.UUID
    quantity: Quantity
    status: CartItemStatus = CartItemStatus.ACTIVE
    price_reference: PriceReference | None = None
    reservation_reference: InventoryReservationReference | None = None
    note: CartNote | None = None
    added_at: datetime | None = None

    def line_total(self) -> Money | None:
        """None if no price has been applied yet -- callers must handle the not-yet-priced case explicitly rather than receiving a fabricated zero total."""
        if self.price_reference is None:
            return None
        return Money(amount=self.price_reference.unit_amount.amount * self.quantity.value, currency=self.price_reference.unit_amount.currency)


@dataclass(slots=True)
class CartSnapshot:
    """Non-root entity, owned by Cart -- a frozen, point-in-time copy of the cart's item state, backing 'Cart Snapshot'/'Cart Versioning'. Stores a simplified, already-serialized representation (not live CartItem references) so restoring it never depends on any cross-module data still being valid."""

    id: uuid.UUID
    token: SnapshotToken
    version_at_capture: int
    captured_at: datetime
    items_snapshot: tuple[dict, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class CartAuditEntry:
    """Non-root entity, owned by Cart -- 'Cart Audit Events' as a queryable, in-aggregate timeline (distinct from the Outbox-published domain events in events.py, which are for cross-module/async consumption; this is a same-aggregate, synchronous history a customer-support view can read directly)."""

    id: uuid.UUID
    action: str
    actor_id: uuid.UUID | None
    occurred_at: datetime
    details: dict = field(default_factory=dict)


@dataclass(slots=True)
class CartValidationIssue:
    """Non-root entity -- one problem found by `CartValidationPolicy`, returned as part of `ValidateCart`'s result. Not persisted as aggregate state (validation is computed fresh on demand), but modeled as an entity per this phase's brief since it has enough structure (severity + code + message + optional item reference) to warrant one rather than a bare tuple."""

    id: uuid.UUID
    severity: CartValidationSeverity
    code: CartValidationIssueCode
    message: str
    item_id: uuid.UUID | None = None


@dataclass(slots=True)
class ShippingEstimateReference:
    """Non-root entity, owned by Cart -- 'Shipping Estimate Reference': a cross-module reference to a shipping estimate computed elsewhere (a future Fulfillment concern), plus the actual estimated amount so Cart can display a total without calling back."""

    shipping_estimate_id: uuid.UUID
    estimated_amount: EstimatedAmount
    estimated_at: datetime


@dataclass(slots=True)
class TaxEstimateReference:
    """Non-root entity, owned by Cart -- 'Tax Estimate Reference', same rationale as ShippingEstimateReference."""

    tax_estimate_id: uuid.UUID
    estimated_amount: EstimatedAmount
    estimated_at: datetime
