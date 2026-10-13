"""
POS aggregates.

**One aggregate root: `Sale`.** A genuinely different shape from every
prior module's own two-aggregate split (Notifications, Analytics) --
POS's own Domain has no second, independently-lifecycled concept.
`SaleLineItem` is an owned entity (see entities.py's own docstring for
the full ownership rationale), not a second aggregate.

**`Sale` owns the in-register transaction lifecycle** -- opening,
adding/removing line items, completing, voiding a not-yet-completed
transaction -- and the whole-sale return of a completed one
(`refund`). A POS sale never becomes an Ordering `Order`, so
Ordering's own OrderReturn/OrderCancellation cannot reach it; the
in-store return is therefore modeled here (product decision).

**Cross-context references remain plain `uuid.UUID` throughout** --
`branch_id` (Store's own `Branch`), `cashier_id`/`customer_id`
(Identity's own `User`), `product_id` (on each `SaleLineItem`,
Products' own aggregate). No concrete model from any other bounded
context is imported anywhere in this file.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.pos.domain.entities import SaleLineItem
from apps.pos.domain.enums import SaleStatus
from apps.pos.domain.events import (
    SaleCompleted,
    SaleCustomerSet,
    SaleLineItemAdded,
    SaleLineItemQuantityUpdated,
    SaleLineItemRemoved,
    SaleOpened,
    SaleRefunded,
    SaleVoided,
)
from apps.pos.domain.exceptions import EmptySale, InvalidSaleTransition, SaleLineItemNotFound
from apps.pos.domain.value_objects import Quantity
from shared.value_objects.money import Money


@dataclass(slots=True)
class Sale:
    """Aggregate root -- one in-register point-of-sale transaction."""

    id: uuid.UUID
    branch_id: uuid.UUID
    cashier_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    status: SaleStatus = SaleStatus.OPEN
    line_items: dict[uuid.UUID, SaleLineItem] = field(default_factory=dict)
    created_at: datetime | None = None
    completed_at: datetime | None = None
    voided_at: datetime | None = None
    refunded_at: datetime | None = None

    # --- Creation ------------------------------------------------------

    @staticmethod
    def open(sale_id: uuid.UUID, branch_id: uuid.UUID, cashier_id: uuid.UUID, at: datetime, customer_id: uuid.UUID | None = None) -> tuple[Sale, SaleOpened]:
        sale = Sale(id=sale_id, branch_id=branch_id, cashier_id=cashier_id, customer_id=customer_id, created_at=at)
        event = SaleOpened(sale_id=sale.id, branch_id=branch_id, cashier_id=cashier_id)
        return sale, event

    # --- Line items ------------------------------------------------------

    def add_line_item(self, product_id: uuid.UUID, quantity: Quantity, unit_price: Money) -> SaleLineItemAdded:
        if self.status != SaleStatus.OPEN:
            raise InvalidSaleTransition(f"Cannot add a line item to a sale in status {self.status.value}; only OPEN sales accept new line items.")
        line_item = SaleLineItem(id=uuid.uuid4(), product_id=product_id, quantity=quantity, unit_price=unit_price)
        self.line_items[line_item.id] = line_item
        return SaleLineItemAdded(sale_id=self.id, line_item_id=line_item.id, product_id=product_id, quantity=quantity.value, unit_price=unit_price.amount)

    def remove_line_item(self, line_item_id: uuid.UUID) -> SaleLineItemRemoved:
        if self.status != SaleStatus.OPEN:
            raise InvalidSaleTransition(f"Cannot remove a line item from a sale in status {self.status.value}; only OPEN sales can be modified.")
        if line_item_id not in self.line_items:
            raise SaleLineItemNotFound(f"No line item '{line_item_id}' exists on this sale.")
        del self.line_items[line_item_id]
        return SaleLineItemRemoved(sale_id=self.id, line_item_id=line_item_id)

    def update_line_item_quantity(self, line_item_id: uuid.UUID, new_quantity: Quantity) -> SaleLineItemQuantityUpdated:
        """
        Real, closed gap: previously the only way to change a line
        item's quantity was remove + re-add (two separate, non-atomic
        API calls, and re-add always created a fresh line item with a
        new id -- the cashier's +/- taps on the cart itself had
        nothing to call). Only OPEN sales accept this, matching
        add_line_item/remove_line_item's own identical guard.
        """
        if self.status != SaleStatus.OPEN:
            raise InvalidSaleTransition(f"Cannot update a line item on a sale in status {self.status.value}; only OPEN sales can be modified.")
        if line_item_id not in self.line_items:
            raise SaleLineItemNotFound(f"No line item '{line_item_id}' exists on this sale.")
        existing = self.line_items[line_item_id]
        self.line_items[line_item_id] = SaleLineItem(id=existing.id, product_id=existing.product_id, quantity=new_quantity, unit_price=existing.unit_price)
        return SaleLineItemQuantityUpdated(sale_id=self.id, line_item_id=line_item_id, new_quantity=new_quantity.value)

    def set_customer(self, customer_id: uuid.UUID) -> SaleCustomerSet:
        """
        Real, closed gap: the premium checkout redesign selects/creates
        the real buyer (an actual `identity.User`) only once the cart is
        already built -- `Sale.open()` is called much earlier, before
        the cashier has scanned a single item, so `customer_id` (only
        ever settable at `open()` time before this) had no real way to
        reach an already-open Sale. Matches every other mutation's own
        identical OPEN-only guard -- a completed or voided sale's real
        buyer is a permanent, closed fact.
        """
        if self.status != SaleStatus.OPEN:
            raise InvalidSaleTransition(f"Cannot set the customer on a sale in status {self.status.value}; only OPEN sales can be modified.")
        self.customer_id = customer_id
        return SaleCustomerSet(sale_id=self.id, customer_id=customer_id)

    # --- Totals ------------------------------------------------------------

    def total(self) -> Money:
        """Computed on demand by summing every line item's own line_total() -- never stored as a separate, potentially-inconsistent field. Returns Money.zero() for a sale with no line items yet."""
        if not self.line_items:
            return Money.zero()
        items = list(self.line_items.values())
        running = items[0].line_total()
        for item in items[1:]:
            running = running + item.line_total()
        return running

    # --- Lifecycle ------------------------------------------------------

    def complete(self, at: datetime) -> SaleCompleted:
        """Mirrors Ordering's own certified EmptyOrder precedent: a sale with zero line items cannot be completed."""
        if self.status != SaleStatus.OPEN:
            raise InvalidSaleTransition(f"Cannot complete a sale in status {self.status.value}; only OPEN sales can be completed.")
        if not self.line_items:
            raise EmptySale("Cannot complete a sale with zero line items.")
        self.status = SaleStatus.COMPLETED
        self.completed_at = at
        total = self.total()
        return SaleCompleted(sale_id=self.id, total_amount=total.amount, currency=total.currency)

    def refund(self, at: datetime) -> SaleRefunded:
        """Whole-sale return: only legal from COMPLETED. Line items and prices stay untouched -- they are the record of what is being returned."""
        if self.status != SaleStatus.COMPLETED:
            raise InvalidSaleTransition(f"Cannot refund a sale in status {self.status.value}; only COMPLETED sales can be refunded.")
        self.status = SaleStatus.REFUNDED
        self.refunded_at = at
        total = self.total()
        return SaleRefunded(sale_id=self.id, total_amount=total.amount, currency=total.currency)

    def void(self, at: datetime) -> SaleVoided:
        """Only legal from OPEN -- a COMPLETED sale is never voided; it is refunded instead (see `refund`)."""
        if self.status != SaleStatus.OPEN:
            raise InvalidSaleTransition(f"Cannot void a sale in status {self.status.value}; only OPEN sales can be voided.")
        self.status = SaleStatus.VOIDED
        self.voided_at = at
        return SaleVoided(sale_id=self.id)
