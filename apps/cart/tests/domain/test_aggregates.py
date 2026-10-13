"""
Cart aggregate tests -- covers every business rule this phase
explicitly names: creation, locking/unlocking, item add/remove/
quantity, guest merge, ownership transfer, coupon/snapshot/reservation
attach-detach, status transitions, validation-relevant state, audit,
version increment, event emission, and edge cases.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from apps.cart.domain.enums import CartItemStatus, CartLockReason, CartStatus, CartType, MergeStrategy
from apps.cart.domain.exceptions import (
    CartAlreadyConverted,
    CartAlreadyLocked,
    CartArchived,
    CartEntityNotFound,
    CartItemNotFound,
    CartLocked,
    CartNotLocked,
    CartOwnershipConflict,
    InvalidCartLifecycleTransition,
    InvalidQuantity,
)
from apps.cart.domain.value_objects import Money
from apps.cart.tests.factories import make_active_cart, make_cart
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def _now() -> datetime:
    return datetime.utcnow()


class TestCartCreation:
    def test_creates_with_defaults(self):
        cart = make_cart()
        assert cart.status == CartStatus.ACTIVE
        assert cart.cart_type == CartType.GUEST
        assert cart.version.value == 1
        assert cart.items == {}


class TestAddItem:
    def test_add_item_creates_new_line(self):
        cart = make_cart()
        variant_id = uuid.uuid4()
        event = cart.add_item(variant_id, 2, _now())
        assert len(cart.items) == 1
        assert event.quantity == 2
        assert event.product_variant_id == variant_id

    def test_add_item_increases_quantity_for_existing_variant(self):
        cart = make_cart()
        variant_id = uuid.uuid4()
        cart.add_item(variant_id, 2, _now())
        event = cart.add_item(variant_id, 3, _now())
        assert len(cart.items) == 1
        assert event.quantity == 5

    def test_add_item_rejects_non_positive_quantity(self):
        cart = make_cart()
        with pytest.raises(InvalidQuantity):
            cart.add_item(uuid.uuid4(), 0, _now())

    def test_add_item_bumps_version(self):
        cart = make_cart()
        cart.add_item(uuid.uuid4(), 1, _now())
        assert cart.version.value == 2

    def test_add_item_writes_audit_entry(self):
        cart = make_cart()
        cart.add_item(uuid.uuid4(), 1, _now())
        assert len(cart.audit_log) == 1
        assert cart.audit_log[0].action == "item_added"

    def test_add_item_on_locked_cart_raises(self):
        cart = make_cart()
        cart.lock(CartLockReason.CHECKOUT_IN_PROGRESS)
        with pytest.raises(CartLocked):
            cart.add_item(uuid.uuid4(), 1, _now())

    def test_add_item_on_archived_cart_raises(self):
        cart = make_cart()
        cart.archive()
        with pytest.raises(CartArchived):
            cart.add_item(uuid.uuid4(), 1, _now())


class TestRemoveItem:
    def test_remove_item_marks_removed(self):
        cart = make_cart()
        event = cart.add_item(uuid.uuid4(), 1, _now())
        cart.remove_item(event.item_id, _now())
        assert cart.items[event.item_id].status == CartItemStatus.REMOVED

    def test_remove_missing_item_raises(self):
        cart = make_cart()
        with pytest.raises(CartItemNotFound):
            cart.remove_item(uuid.uuid4(), _now())

    def test_remove_item_on_locked_cart_raises(self):
        cart = make_cart()
        event = cart.add_item(uuid.uuid4(), 1, _now())
        cart.lock(CartLockReason.ADMIN_HOLD)
        with pytest.raises(CartLocked):
            cart.remove_item(event.item_id, _now())


class TestUpdateQuantity:
    def test_update_quantity_success(self):
        cart = make_cart()
        added = cart.add_item(uuid.uuid4(), 1, _now())
        event = cart.update_quantity(added.item_id, 10, _now())
        assert event.old_quantity == 1
        assert event.new_quantity == 10

    def test_update_quantity_rejects_non_positive(self):
        cart = make_cart()
        added = cart.add_item(uuid.uuid4(), 1, _now())
        with pytest.raises(InvalidQuantity):
            cart.update_quantity(added.item_id, 0, _now())

    def test_update_missing_item_raises(self):
        cart = make_cart()
        with pytest.raises(CartItemNotFound):
            cart.update_quantity(uuid.uuid4(), 5, _now())

    def test_bulk_update_all_or_nothing(self):
        cart = make_cart()
        added = cart.add_item(uuid.uuid4(), 1, _now())
        with pytest.raises(CartItemNotFound):
            cart.bulk_update_items({added.item_id: 5, uuid.uuid4(): 3}, _now())
        # The valid item must NOT have been updated either -- all-or-nothing.
        assert cart.items[added.item_id].quantity.value == 1

    def test_bulk_update_success(self):
        cart = make_cart()
        a = cart.add_item(uuid.uuid4(), 1, _now())
        b = cart.add_item(uuid.uuid4(), 1, _now())
        events = cart.bulk_update_items({a.item_id: 3, b.item_id: 4}, _now())
        assert len(events) == 2
        assert cart.items[a.item_id].quantity.value == 3


class TestClearCart:
    def test_clear_marks_all_removed(self):
        cart = make_cart()
        cart.add_item(uuid.uuid4(), 1, _now())
        cart.add_item(uuid.uuid4(), 1, _now())
        event = cart.clear(_now())
        assert event.items_removed == 2
        assert all(i.status == CartItemStatus.REMOVED for i in cart.items.values())


class TestCouponReference:
    def test_apply_and_remove(self):
        cart = make_cart()
        coupon_id = uuid.uuid4()
        cart.apply_coupon_reference(coupon_id, _now())
        assert coupon_id in cart.coupon_ids
        cart.remove_coupon_reference(coupon_id, _now())
        assert coupon_id not in cart.coupon_ids


class TestPriceSnapshotReference:
    def test_attach_clears_price_changed_status(self):
        cart = make_cart()
        added = cart.add_item(uuid.uuid4(), 1, _now())
        cart.items[added.item_id].status = CartItemStatus.PRICE_CHANGED
        cart.attach_price_snapshot(added.item_id, uuid.uuid4(), Money(amount=Decimal("10.00"), currency="UZS"), _now())
        assert cart.items[added.item_id].status == CartItemStatus.ACTIVE

    def test_detach_clears_reference(self):
        cart = make_cart()
        added = cart.add_item(uuid.uuid4(), 1, _now())
        cart.attach_price_snapshot(added.item_id, uuid.uuid4(), Money(amount=Decimal("10.00"), currency="UZS"), _now())
        cart.detach_price_snapshot(added.item_id)
        assert cart.items[added.item_id].price_reference is None

    def test_attach_missing_item_raises(self):
        cart = make_cart()
        with pytest.raises(CartItemNotFound):
            cart.attach_price_snapshot(uuid.uuid4(), uuid.uuid4(), Money(amount=Decimal("10.00"), currency="UZS"), _now())


class TestReservationReference:
    def test_attach_and_detach(self):
        cart = make_cart()
        added = cart.add_item(uuid.uuid4(), 1, _now())
        reservation_id = uuid.uuid4()
        cart.attach_reservation(added.item_id, reservation_id, _now())
        assert cart.items[added.item_id].reservation_reference.reservation_id == reservation_id
        cart.detach_reservation(added.item_id)
        assert cart.items[added.item_id].reservation_reference is None


class TestLockingUnlocking:
    def test_lock_then_unlock(self):
        cart = make_cart()
        event = cart.lock(CartLockReason.CHECKOUT_IN_PROGRESS)
        assert cart.lock_reason == CartLockReason.CHECKOUT_IN_PROGRESS
        assert event.reason == "checkout_in_progress"
        cart.unlock()
        assert cart.lock_reason is None

    def test_double_lock_raises(self):
        cart = make_cart()
        cart.lock(CartLockReason.ADMIN_HOLD)
        with pytest.raises(CartAlreadyLocked):
            cart.lock(CartLockReason.FRAUD_REVIEW)

    def test_unlock_unlocked_cart_raises(self):
        cart = make_cart()
        with pytest.raises(CartNotLocked):
            cart.unlock()


class TestStatusTransitions:
    def test_save_from_active(self):
        cart = make_cart()
        event = cart.save()
        assert cart.status == CartStatus.SAVED
        assert event.cart_id == cart.id

    def test_save_non_active_raises(self):
        cart = make_cart()
        cart.archive()
        with pytest.raises(InvalidCartLifecycleTransition):
            cart.save()

    def test_archive_then_restore(self):
        cart = make_cart()
        cart.archive()
        assert cart.status == CartStatus.ARCHIVED
        event = cart.restore()
        assert cart.status == CartStatus.ACTIVE
        assert event.cart_id == cart.id

    def test_archive_twice_raises(self):
        cart = make_cart()
        cart.archive()
        with pytest.raises(InvalidCartLifecycleTransition):
            cart.archive()

    def test_archive_converted_cart_raises(self):
        cart = make_cart(status=CartStatus.CONVERTED)
        with pytest.raises(CartAlreadyConverted):
            cart.archive()

    def test_expire_active_cart(self):
        cart = make_cart(expires_at=_now() - timedelta(minutes=1))
        event = cart.expire(_now())
        assert cart.status == CartStatus.EXPIRED
        assert event.cart_id == cart.id

    def test_expire_before_expiry_time_raises(self):
        cart = make_cart(expires_at=_now() + timedelta(hours=1))
        with pytest.raises(ValidationFailed):
            cart.expire(_now())

    def test_expire_already_archived_raises(self):
        cart = make_cart()
        cart.archive()
        with pytest.raises(InvalidCartLifecycleTransition):
            cart.expire(_now())

    def test_restore_active_cart_raises(self):
        cart = make_cart()
        with pytest.raises(InvalidCartLifecycleTransition):
            cart.restore()

    def test_mutation_on_converted_cart_raises(self):
        cart = make_cart(status=CartStatus.CONVERTED)
        with pytest.raises(CartAlreadyConverted):
            cart.add_item(uuid.uuid4(), 1, _now())


class TestOwnershipTransfer:
    def test_assign_customer_converts_guest_to_authenticated(self):
        cart = make_cart()
        customer_id = uuid.uuid4()
        event = cart.assign_customer(customer_id, _now())
        assert cart.customer_id == customer_id
        assert cart.cart_type == CartType.AUTHENTICATED
        assert event.customer_id == customer_id

    def test_assign_same_customer_twice_is_idempotent(self):
        cart = make_cart()
        customer_id = uuid.uuid4()
        cart.assign_customer(customer_id, _now())
        cart.assign_customer(customer_id, _now())  # should not raise
        assert cart.customer_id == customer_id

    def test_assign_different_customer_raises(self):
        cart = make_cart()
        cart.assign_customer(uuid.uuid4(), _now())
        with pytest.raises(CartOwnershipConflict):
            cart.assign_customer(uuid.uuid4(), _now())


class TestGuestMerge:
    def test_sum_quantities_strategy(self):
        auth_cart = make_cart(cart_type=CartType.AUTHENTICATED)
        guest_cart = make_cart()
        variant_id = uuid.uuid4()
        auth_cart.add_item(variant_id, 2, _now())
        guest_cart.add_item(variant_id, 3, _now())

        result, event = auth_cart.merge_guest_cart(guest_cart, MergeStrategy.SUM_QUANTITIES, _now())
        merged_item = next(i for i in auth_cart.items.values() if i.product_variant_id == variant_id)
        assert merged_item.quantity.value == 5
        assert result.items_merged == 1
        assert event.target_cart_id == auth_cart.id
        assert event.source_cart_id == guest_cart.id

    def test_keep_authenticated_strategy_skips_conflicts(self):
        auth_cart = make_cart(cart_type=CartType.AUTHENTICATED)
        guest_cart = make_cart()
        shared_variant = uuid.uuid4()
        guest_only_variant = uuid.uuid4()
        auth_cart.add_item(shared_variant, 2, _now())
        guest_cart.add_item(shared_variant, 5, _now())
        guest_cart.add_item(guest_only_variant, 1, _now())

        result, _ = auth_cart.merge_guest_cart(guest_cart, MergeStrategy.KEEP_AUTHENTICATED, _now())
        shared_item = next(i for i in auth_cart.items.values() if i.product_variant_id == shared_variant)
        assert shared_item.quantity.value == 2  # unchanged -- authenticated wins
        assert result.items_merged == 1
        assert result.items_skipped == 1

    def test_replace_with_guest_strategy(self):
        auth_cart = make_cart(cart_type=CartType.AUTHENTICATED)
        guest_cart = make_cart()
        auth_cart.add_item(uuid.uuid4(), 2, _now())
        guest_variant = uuid.uuid4()
        guest_cart.add_item(guest_variant, 5, _now())

        result, _ = auth_cart.merge_guest_cart(guest_cart, MergeStrategy.REPLACE_WITH_GUEST, _now())
        active_items = [i for i in auth_cart.items.values() if i.status != CartItemStatus.REMOVED]
        assert len(active_items) == 1
        assert active_items[0].product_variant_id == guest_variant
        assert result.items_replaced == 1

    def test_merge_does_not_mutate_guest_cart(self):
        auth_cart = make_cart(cart_type=CartType.AUTHENTICATED)
        guest_cart = make_cart()
        guest_cart.add_item(uuid.uuid4(), 3, _now())
        guest_item_count_before = len(guest_cart.items)

        auth_cart.merge_guest_cart(guest_cart, MergeStrategy.SUM_QUANTITIES, _now())
        assert len(guest_cart.items) == guest_item_count_before
        assert guest_cart.status == CartStatus.ACTIVE  # merge itself never archives the source


class TestSnapshotCreateAndRestore:
    def test_create_snapshot(self):
        cart = make_cart()
        cart.add_item(uuid.uuid4(), 3, _now())
        snapshot, event = cart.create_snapshot(_now())
        assert len(cart.snapshots) == 1
        assert snapshot.version_at_capture == cart.version.value
        assert event.snapshot_id == snapshot.id

    def test_restore_snapshot_replaces_items(self):
        cart = make_cart()
        cart.add_item(uuid.uuid4(), 3, _now())
        snapshot, _ = cart.create_snapshot(_now())
        cart.add_item(uuid.uuid4(), 1, _now())  # add another item after the snapshot

        event = cart.restore_snapshot(snapshot.id, _now())
        active_items = [i for i in cart.items.values() if i.status != CartItemStatus.REMOVED]
        assert len(active_items) == 1
        assert active_items[0].quantity.value == 3
        assert event.snapshot_id == snapshot.id

    def test_restore_missing_snapshot_raises(self):
        cart = make_cart()
        with pytest.raises(CartEntityNotFound):
            cart.restore_snapshot(uuid.uuid4(), _now())

    def test_restore_snapshot_on_locked_cart_raises(self):
        cart = make_cart()
        cart.add_item(uuid.uuid4(), 1, _now())
        snapshot, _ = cart.create_snapshot(_now())
        cart.lock(CartLockReason.ADMIN_HOLD)
        with pytest.raises(CartLocked):
            cart.restore_snapshot(snapshot.id, _now())


class TestCheckoutReadiness:
    def test_empty_cart_not_ready(self):
        cart = make_cart()
        assert cart.structural_checkout_readiness().value == "not_ready"

    def test_active_priced_cart_is_ready(self):
        cart = make_active_cart()
        assert cart.structural_checkout_readiness().value == "ready"

    def test_locked_cart_is_blocked(self):
        cart = make_active_cart()
        cart.lock(CartLockReason.CHECKOUT_IN_PROGRESS)
        assert cart.structural_checkout_readiness().value == "blocked"

    def test_unpriced_item_not_ready(self):
        cart = make_cart()
        cart.add_item(uuid.uuid4(), 1, _now())
        assert cart.structural_checkout_readiness().value == "not_ready"

    def test_out_of_stock_item_is_blocked(self):
        cart = make_active_cart()
        item = next(iter(cart.items.values()))
        item.status = CartItemStatus.OUT_OF_STOCK
        assert cart.structural_checkout_readiness().value == "blocked"


class TestVersionIncrement:
    def test_every_mutating_call_bumps_version(self):
        cart = make_cart()
        assert cart.version.value == 1
        added = cart.add_item(uuid.uuid4(), 1, _now())
        assert cart.version.value == 2
        cart.update_quantity(added.item_id, 2, _now())
        assert cart.version.value == 3
        cart.remove_item(added.item_id, _now())
        assert cart.version.value == 4
