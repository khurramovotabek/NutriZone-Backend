"""
Ordering domain services -- pure business rules with no I/O, per MIC
§4, matching every prior module's domain/services.py pattern.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from apps.ordering.domain.entities import OrderLineItem
from apps.ordering.domain.enums import OrderStatus
from apps.ordering.domain.value_objects import Money, OrderTotal, ReturnWindow

DEFAULT_ORDER_EXPIRY = timedelta(hours=2)


class CheckoutPolicy:
    """Decides whether a cart (represented here by the data the Application layer already extracted from it, not a live Cart reference) is eligible to become an Order."""

    @staticmethod
    def is_eligible(has_items: bool, all_items_priced: bool, is_locked: bool) -> bool:
        return has_items and all_items_priced and not is_locked


class OrderCreationPolicy:
    """Validates the preconditions for `Order.create_from_cart_data()` before the aggregate factory is even called -- lets the Application layer fail fast with a clear reason rather than relying solely on the aggregate's own `EmptyOrder` check."""

    @staticmethod
    def validate_preconditions(line_count: int, shipping_address_present: bool, billing_address_present: bool) -> list[str]:
        problems = []
        if line_count == 0:
            problems.append("Cart has no items to convert into an order.")
        if not shipping_address_present:
            problems.append("No shipping address was supplied.")
        if not billing_address_present:
            problems.append("No billing address was supplied.")
        return problems


class OrderValidationPolicy:
    @staticmethod
    def validate_currency_consistency(lines: list[OrderLineItem], order_currency: str) -> list[str]:
        mismatched = [l.id for l in lines if l.unit_price.currency != order_currency]
        return [f"Line item {line_id} currency does not match order currency {order_currency}." for line_id in mismatched]


class OrderExpirationPolicy:
    """Governs how long a DRAFT/PENDING_PAYMENT order may remain unconfirmed before it should expire -- mirrors `apps.cart.domain.services.ExpirationPolicy`'s shape exactly."""

    @staticmethod
    def compute_expiry(created_at: datetime) -> datetime:
        return created_at + DEFAULT_ORDER_EXPIRY

    @staticmethod
    def is_due_for_expiry(created_at: datetime, at: datetime) -> bool:
        return at >= OrderExpirationPolicy.compute_expiry(created_at)


class CancellationPolicy:
    @staticmethod
    def is_eligible_for_direct_cancellation(status: OrderStatus) -> bool:
        return status in (OrderStatus.DRAFT, OrderStatus.PENDING_PAYMENT, OrderStatus.CONFIRMED, OrderStatus.PROCESSING)

    @staticmethod
    def requires_formal_approval(status: OrderStatus) -> bool:
        """Once shipped, a cancellation can no longer be an instant self-service action -- it must go through OrderCancellation's formal request/approve workflow."""
        return status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED)


class ReturnEligibilityPolicy:
    @staticmethod
    def is_eligible(order_status: OrderStatus, delivered_at: datetime | None, at: datetime, window: ReturnWindow) -> bool:
        if order_status not in (OrderStatus.DELIVERED, OrderStatus.COMPLETED):
            return False
        if delivered_at is None:
            return False
        return window.is_within_window(delivered_at, at)


class InvoiceNumberPolicy:
    """A pure formatting policy -- the actual sequential numbering authority lives at the Infrastructure layer (a database sequence), this only defines the format every invoice number must match."""

    @staticmethod
    def format(sequence: int, year: int) -> str:
        return f"INV-{year}-{sequence:08d}"
