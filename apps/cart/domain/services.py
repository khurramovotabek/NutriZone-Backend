"""
Cart domain services.

Pure business rules with no I/O, per MIC §4 -- handed data by the
calling Application Service, never fetching it themselves. Matches
every prior module's domain/services.py pattern.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from apps.cart.domain.entities import CartItem, CartValidationIssue
from apps.cart.domain.enums import CartItemStatus, CartValidationIssueCode, CartValidationSeverity, CheckoutReadiness, MergeStrategy
from apps.cart.domain.value_objects import ExpirationPeriod, Money

DEFAULT_MAX_QUANTITY_PER_ITEM = 999
DEFAULT_CART_TTL = ExpirationPeriod(timedelta(days=30))
DEFAULT_GUEST_CART_TTL = ExpirationPeriod(timedelta(days=7))


class CartMergePolicy:
    """Decides which MergeStrategy applies for a given guest->authenticated login event -- kept separate from `Cart.merge_guest_cart()` (which only executes a strategy already chosen) so the choice itself is independently testable and can evolve (e.g. a future 'ask the customer' UX) without touching the aggregate."""

    @staticmethod
    def recommend_strategy(guest_cart_item_count: int, authenticated_cart_item_count: int) -> MergeStrategy:
        if authenticated_cart_item_count == 0:
            return MergeStrategy.REPLACE_WITH_GUEST
        if guest_cart_item_count == 0:
            return MergeStrategy.KEEP_AUTHENTICATED
        return MergeStrategy.SUM_QUANTITIES


class QuantityPolicy:
    @staticmethod
    def assert_within_max(quantity: int, max_quantity: int = DEFAULT_MAX_QUANTITY_PER_ITEM) -> None:
        from apps.cart.domain.exceptions import InvalidQuantity

        if quantity > max_quantity:
            raise InvalidQuantity(f"Quantity {quantity} exceeds the maximum allowed per line item ({max_quantity}).")


class ExpirationPolicy:
    @staticmethod
    def compute_expiry(created_or_last_active_at: datetime, is_guest: bool) -> datetime:
        period = DEFAULT_GUEST_CART_TTL if is_guest else DEFAULT_CART_TTL
        return period.expires_from(created_or_last_active_at)

    @staticmethod
    def is_due_for_expiry(expires_at: datetime | None, at: datetime) -> bool:
        return expires_at is not None and at >= expires_at


class SnapshotPolicy:
    """Retention rule for 'Cart Versioning' -- how many CartSnapshots a single cart is allowed to accumulate before the oldest must be pruned. A pure count check; actual pruning is an Application Service's job (it decides which existing snapshot to drop, this only says whether one more can be added)."""

    MAX_SNAPSHOTS_PER_CART = 20

    @staticmethod
    def can_add_snapshot(current_snapshot_count: int) -> bool:
        return current_snapshot_count < SnapshotPolicy.MAX_SNAPSHOTS_PER_CART

    @staticmethod
    def oldest_snapshot_id_to_prune(snapshots_by_captured_at: list[tuple[uuid.UUID, datetime]]) -> uuid.UUID | None:
        if not snapshots_by_captured_at:
            return None
        return min(snapshots_by_captured_at, key=lambda pair: pair[1])[0]


class CartValidationPolicy:
    """
    'Cart Validation' -- inspects a cart's current items and produces
    a list of `CartValidationIssue`s. Handed the items directly (plus
    any external signals the caller already gathered, e.g. whether an
    item's stock is confirmed) rather than reaching into Inventory
    itself.
    """

    @staticmethod
    def validate(items: list[CartItem], is_locked: bool, is_expired: bool, currency: str) -> list[CartValidationIssue]:
        issues: list[CartValidationIssue] = []
        active_items = [i for i in items if i.status != CartItemStatus.REMOVED]

        if not active_items:
            issues.append(CartValidationIssue(id=uuid.uuid4(), severity=CartValidationSeverity.ERROR, code=CartValidationIssueCode.EMPTY_CART, message="The cart has no active items."))

        if is_locked:
            issues.append(CartValidationIssue(id=uuid.uuid4(), severity=CartValidationSeverity.ERROR, code=CartValidationIssueCode.CART_LOCKED, message="The cart is locked."))

        if is_expired:
            issues.append(CartValidationIssue(id=uuid.uuid4(), severity=CartValidationSeverity.ERROR, code=CartValidationIssueCode.CART_EXPIRED, message="The cart has expired."))

        for item in active_items:
            if item.status == CartItemStatus.OUT_OF_STOCK:
                issues.append(CartValidationIssue(id=uuid.uuid4(), severity=CartValidationSeverity.ERROR, code=CartValidationIssueCode.ITEM_OUT_OF_STOCK, message="An item in the cart is out of stock.", item_id=item.id))
            if item.status == CartItemStatus.PRICE_CHANGED:
                issues.append(CartValidationIssue(id=uuid.uuid4(), severity=CartValidationSeverity.WARNING, code=CartValidationIssueCode.ITEM_PRICE_CHANGED, message="An item's price has changed since it was added.", item_id=item.id))
            if item.status == CartItemStatus.INVALID:
                issues.append(CartValidationIssue(id=uuid.uuid4(), severity=CartValidationSeverity.ERROR, code=CartValidationIssueCode.ITEM_INVALID, message="An item in the cart is no longer valid.", item_id=item.id))
            if item.price_reference is None:
                issues.append(CartValidationIssue(id=uuid.uuid4(), severity=CartValidationSeverity.WARNING, code=CartValidationIssueCode.NO_PRICE_SNAPSHOT, message="An item has no applied price snapshot.", item_id=item.id))
            elif item.price_reference.unit_amount.currency != currency:
                issues.append(CartValidationIssue(id=uuid.uuid4(), severity=CartValidationSeverity.ERROR, code=CartValidationIssueCode.CURRENCY_MISMATCH, message="An item's price currency does not match the cart's currency.", item_id=item.id))

        return issues

    @staticmethod
    def has_blocking_errors(issues: list[CartValidationIssue]) -> bool:
        return any(i.severity == CartValidationSeverity.ERROR for i in issues)


class CheckoutReadinessPolicy:
    """
    Fuller checkout-readiness check than `Cart.structural_checkout_
    readiness()` -- accepts additional externally-gathered signals
    (e.g. whether every item's reservation is still valid, confirmed
    by the caller against Inventory) that the bare aggregate state
    alone cannot determine.
    """

    @staticmethod
    def evaluate(structural_readiness: CheckoutReadiness, all_reservations_valid: bool, validation_issues: list[CartValidationIssue]) -> CheckoutReadiness:
        if structural_readiness == CheckoutReadiness.BLOCKED:
            return CheckoutReadiness.BLOCKED
        if CartValidationPolicy.has_blocking_errors(validation_issues):
            return CheckoutReadiness.BLOCKED
        if not all_reservations_valid:
            return CheckoutReadiness.NOT_READY
        return structural_readiness


class CurrencyConversionPolicy:
    """
    'Currency Conversion' -- Cart never computes exchange rates
    itself; every conversion is caller-supplied (a future Pricing/FX
    module's job). This policy only validates that a supplied
    converted amount is structurally sane (non-negative, correct
    target currency) -- it never invents a rate.
    """

    @staticmethod
    def apply_supplied_conversion(original: Money, converted_amount: Money, target_currency: str) -> Money:
        from common.exceptions import ValidationFailed

        if converted_amount.currency != target_currency:
            raise ValidationFailed(f"Converted amount's currency '{converted_amount.currency}' does not match the requested target currency '{target_currency}'.")
        return converted_amount
