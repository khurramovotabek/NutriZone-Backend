"""
Aggregate tests -- covers every business rule this phase explicitly
names across all 3 aggregates.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from apps.ordering.domain.aggregates import Order, OrderCancellation, OrderReturn
from apps.ordering.domain.enums import (
    FulfillmentReferenceStatus, OrderChannel, OrderFailureReason, OrderLockReason, PaymentReferenceStatus,
)
from apps.ordering.domain.exceptions import (
    CancellationQuantityExceedsOrdered, EmptyOrder, FulfillmentReferenceNotFound, InvalidCancellationLifecycleTransition,
    InvalidInvoiceLifecycleTransition, InvalidOrderArchivalTransition, InvalidOrderLifecycleTransition,
    InvalidReturnLifecycleTransition, InvoiceAlreadyIssued, OrderAlreadyCancelled, OrderAlreadyCompleted,
    OrderAlreadyLocked, OrderLineItemNotFound, OrderLocked, OrderNotEligibleForCancellation, OrderNotLocked,
    OrderNotModifiable, PaymentReferenceNotFound, ReturnQuantityExceedsOrdered, ReturnWindowExpired,
)
from apps.ordering.domain.value_objects import Money, OrderNumber, ReturnWindow
from apps.ordering.tests.factories import make_address, make_confirmed_order, make_delivered_order, make_line_item, make_order, make_order_with_line

pytestmark = pytest.mark.unit


def _now() -> datetime:
    return datetime.utcnow()


class TestCreateOrderFromCart:
    def test_creates_pending_payment_order(self):
        line = make_line_item()
        order, event = Order.create_from_cart_data(
            order_id=uuid.uuid4(), order_number=OrderNumber("ORD-TESTCREATE"),
            cart_id=uuid.uuid4(), customer_id=uuid.uuid4(), shipping_address=make_address(), billing_address=make_address(),
            currency="UZS", lines=[line], coupon_ids=set(), channel=OrderChannel.WEB, at=_now(),
        )
        assert order.status.value == "pending_payment"
        assert event.order_id == order.id
        assert len(order.status_history) == 1

    def test_rejects_empty_line_list(self):
        with pytest.raises(EmptyOrder):
            Order.create_from_cart_data(order_id=uuid.uuid4(), order_number=OrderNumber("ORD-TESTEMPTY1"), cart_id=None, customer_id=None, shipping_address=make_address(), billing_address=make_address(), currency="UZS", lines=[], coupon_ids=set(), channel=OrderChannel.WEB, at=_now())


class TestStatusTransitionChain:
    def test_confirm_from_pending_payment(self):
        order = make_order_with_line()
        event = order.confirm(_now())
        assert order.status.value == "confirmed"
        assert event.order_id == order.id

    def test_confirm_wrong_status_raises(self):
        order = make_confirmed_order()
        with pytest.raises(InvalidOrderLifecycleTransition):
            order.confirm(_now())

    def test_full_happy_path_chain(self):
        order = make_confirmed_order()
        order.start_processing(_now())
        assert order.status.value == "processing"
        order.ship(_now())
        assert order.status.value == "shipped"
        order.deliver(_now())
        assert order.status.value == "delivered"
        order.complete(_now())
        assert order.status.value == "completed"
        assert len(order.status_history) == 5  # confirm(from make_confirmed_order) + processing + ship + deliver + complete -- no synthetic "created" entry, since this factory constructs the Order via the raw dataclass constructor, not the real create_from_cart_data() flow that would add one

    def test_start_processing_wrong_status_raises(self):
        order = make_order_with_line()
        with pytest.raises(InvalidOrderLifecycleTransition):
            order.start_processing(_now())

    def test_ship_wrong_status_raises(self):
        order = make_confirmed_order()
        with pytest.raises(InvalidOrderLifecycleTransition):
            order.ship(_now())

    def test_deliver_wrong_status_raises(self):
        order = make_confirmed_order()
        with pytest.raises(InvalidOrderLifecycleTransition):
            order.deliver(_now())

    def test_complete_wrong_status_raises(self):
        order = make_confirmed_order()
        with pytest.raises(InvalidOrderLifecycleTransition):
            order.complete(_now())

    def test_version_increments_on_every_transition(self):
        order = make_order_with_line()
        assert order.version.value == 1
        order.confirm(_now())
        assert order.version.value == 2
        order.start_processing(_now())
        assert order.version.value == 3


class TestCancelAndFail:
    def test_cancel_from_pending_payment(self):
        order = make_order_with_line()
        event = order.cancel("customer_request", _now())
        assert order.status.value == "cancelled"
        assert event.reason == "customer_request"

    def test_cancel_already_cancelled_raises(self):
        order = make_order_with_line()
        order.cancel("customer_request", _now())
        with pytest.raises(OrderAlreadyCancelled):
            order.cancel("customer_request", _now())

    def test_cancel_completed_order_raises(self):
        order = make_delivered_order()
        order.complete(_now())
        with pytest.raises(OrderAlreadyCompleted):
            order.cancel("customer_request", _now())

    def test_cancel_shipped_order_raises_not_eligible(self):
        order = make_confirmed_order()
        order.start_processing(_now())
        order.ship(_now())
        with pytest.raises(OrderNotEligibleForCancellation):
            order.cancel("customer_request", _now())

    def test_fail_from_pending_payment(self):
        order = make_order_with_line()
        event = order.fail(OrderFailureReason.PAYMENT_DECLINED, "Card declined", _now())
        assert order.status.value == "failed"
        assert len(order.failures) == 1
        assert event.reason == "payment_declined"

    def test_fail_confirmed_order_raises(self):
        order = make_confirmed_order()
        with pytest.raises(InvalidOrderLifecycleTransition):
            order.fail(OrderFailureReason.SYSTEM_ERROR, "x", _now())


class TestLineItemCancelAndReturn:
    def test_mark_line_cancelled_full_quantity(self):
        order = make_order_with_line()
        line_id = next(iter(order.lines))
        line = order.lines[line_id]
        event = order.mark_line_cancelled(line_id, line.quantity, _now())
        assert order.lines[line_id].status.value == "cancelled"
        assert event.quantity == line.quantity

    def test_mark_line_cancelled_missing_line_raises(self):
        order = make_order_with_line()
        with pytest.raises(OrderLineItemNotFound):
            order.mark_line_cancelled(uuid.uuid4(), 1, _now())

    def test_mark_line_cancelled_exceeding_ordered_raises(self):
        order = make_order_with_line()
        line_id = next(iter(order.lines))
        with pytest.raises(CancellationQuantityExceedsOrdered):
            order.mark_line_cancelled(line_id, 9999, _now())

    def test_mark_line_returned_full_quantity(self):
        order = make_order_with_line()
        line_id = next(iter(order.lines))
        line = order.lines[line_id]
        event = order.mark_line_returned(line_id, line.quantity, _now())
        assert order.lines[line_id].status.value == "returned"
        assert event.quantity == line.quantity

    def test_mark_line_returned_exceeding_ordered_raises(self):
        order = make_order_with_line()
        line_id = next(iter(order.lines))
        with pytest.raises(ReturnQuantityExceedsOrdered):
            order.mark_line_returned(line_id, 9999, _now())


class TestPaymentAndFulfillmentReferences:
    def test_attach_payment_reference(self):
        order = make_order_with_line()
        event = order.attach_payment_reference(uuid.uuid4(), Money(amount=Decimal("100.00"), currency="UZS"))
        assert len(order.payment_references) == 1
        assert event.payment_id is not None

    def test_update_payment_status(self):
        order = make_order_with_line()
        order.attach_payment_reference(uuid.uuid4(), Money(amount=Decimal("100.00"), currency="UZS"))
        ref_id = next(iter(order.payment_references))
        event = order.update_payment_status(ref_id, PaymentReferenceStatus.CAPTURED, _now())
        assert order.payment_references[ref_id].status == PaymentReferenceStatus.CAPTURED
        assert event.status == "captured"

    def test_update_payment_status_missing_raises(self):
        order = make_order_with_line()
        with pytest.raises(PaymentReferenceNotFound):
            order.update_payment_status(uuid.uuid4(), PaymentReferenceStatus.CAPTURED, _now())

    def test_attach_fulfillment_reference(self):
        order = make_order_with_line()
        event = order.attach_fulfillment_reference(uuid.uuid4())
        assert len(order.fulfillment_references) == 1
        assert event.fulfillment_id is not None

    def test_update_fulfillment_status_sets_shipped_at(self):
        order = make_order_with_line()
        order.attach_fulfillment_reference(uuid.uuid4())
        ref_id = next(iter(order.fulfillment_references))
        now = _now()
        order.update_fulfillment_status(ref_id, FulfillmentReferenceStatus.SHIPPED, now)
        assert order.fulfillment_references[ref_id].shipped_at == now

    def test_update_fulfillment_status_missing_raises(self):
        order = make_order_with_line()
        with pytest.raises(FulfillmentReferenceNotFound):
            order.update_fulfillment_status(uuid.uuid4(), FulfillmentReferenceStatus.SHIPPED, _now())


class TestInvoice:
    def test_issue_invoice(self):
        order = make_order_with_line()
        event = order.issue_invoice("INV-2026-00000001", Money(amount=Decimal("100.00"), currency="UZS"), _now())
        assert order.invoice.status.value == "issued"
        assert event.invoice_number == "INV-2026-00000001"

    def test_issue_invoice_twice_raises(self):
        order = make_order_with_line()
        order.issue_invoice("INV-2026-00000001", Money(amount=Decimal("100.00"), currency="UZS"), _now())
        with pytest.raises(InvoiceAlreadyIssued):
            order.issue_invoice("INV-2026-00000002", Money(amount=Decimal("100.00"), currency="UZS"), _now())


class TestLockUnlockArchiveRestore:
    def test_lock_then_unlock(self):
        order = make_order_with_line()
        event = order.lock(OrderLockReason.FRAUD_REVIEW)
        assert order.lock_reason == OrderLockReason.FRAUD_REVIEW
        assert event.reason == "fraud_review"
        order.unlock()
        assert order.lock_reason is None

    def test_double_lock_raises(self):
        order = make_order_with_line()
        order.lock(OrderLockReason.FRAUD_REVIEW)
        with pytest.raises(OrderAlreadyLocked):
            order.lock(OrderLockReason.DISPUTE)

    def test_unlock_unlocked_raises(self):
        order = make_order_with_line()
        with pytest.raises(OrderNotLocked):
            order.unlock()

    def test_locked_order_blocks_mutation(self):
        order = make_order_with_line()
        order.lock(OrderLockReason.FRAUD_REVIEW)
        with pytest.raises(OrderLocked):
            order.apply_coupon_reference(uuid.uuid4())

    def test_archive_then_restore(self):
        order = make_order_with_line()
        event = order.archive()
        assert order.is_archived is True
        assert event.order_id == order.id
        restore_event = order.restore()
        assert order.is_archived is False
        assert restore_event.order_id == order.id

    def test_archive_twice_raises(self):
        order = make_order_with_line()
        order.archive()
        with pytest.raises(InvalidOrderArchivalTransition):
            order.archive()

    def test_restore_not_archived_raises(self):
        order = make_order_with_line()
        with pytest.raises(InvalidOrderArchivalTransition):
            order.restore()

    def test_archive_is_orthogonal_to_status(self):
        """Archiving a completed order does not change its OrderStatus -- a deliberate design choice, verified here."""
        order = make_delivered_order()
        order.complete(_now())
        order.archive()
        assert order.status.value == "completed"
        assert order.is_archived is True


class TestCouponAndAddress:
    def test_apply_coupon_reference(self):
        order = make_order_with_line()
        coupon_id = uuid.uuid4()
        order.apply_coupon_reference(coupon_id)
        assert coupon_id in order.coupon_ids

    def test_apply_coupon_on_confirmed_order_raises(self):
        order = make_confirmed_order()
        with pytest.raises(OrderNotModifiable):
            order.apply_coupon_reference(uuid.uuid4())

    def test_update_addresses(self):
        order = make_order_with_line()
        new_address = make_address(city="Samarkand")
        order.update_addresses(shipping_address=new_address)
        assert order.shipping_address.city == "Samarkand"

    def test_update_addresses_on_confirmed_order_raises(self):
        order = make_confirmed_order()
        with pytest.raises(OrderNotModifiable):
            order.update_addresses(shipping_address=make_address(city="Samarkand"))


class TestReattachReferences:
    def test_reattach_line_reservation(self):
        order = make_order_with_line()
        line_id = next(iter(order.lines))
        reservation_id = uuid.uuid4()
        order.reattach_line_reservation(line_id, reservation_id)
        assert order.lines[line_id].reservation_id == reservation_id

    def test_reattach_line_reservation_missing_line_raises(self):
        order = make_order_with_line()
        with pytest.raises(OrderLineItemNotFound):
            order.reattach_line_reservation(uuid.uuid4(), uuid.uuid4())

    def test_reattach_line_price_snapshot(self):
        order = make_order_with_line()
        line_id = next(iter(order.lines))
        snapshot_id = uuid.uuid4()
        order.reattach_line_price_snapshot(line_id, snapshot_id)
        assert order.lines[line_id].price_snapshot_id == snapshot_id


class TestOrderReturnAggregate:
    def _return(self) -> OrderReturn:
        from apps.ordering.tests.factories import make_return

        return make_return()

    def test_approve_then_receive_then_refund(self):
        order_return = self._return()
        order_return.approve(_now())
        assert order_return.status.value == "approved"
        order_return.receive(_now())
        assert order_return.status.value == "received"
        event = order_return.refund(Money(amount=Decimal("50.00"), currency="UZS"), _now())
        assert order_return.status.value == "refunded"
        assert event.refund_amount == "50.00"

    def test_reject_from_requested(self):
        order_return = self._return()
        event = order_return.reject("not eligible", _now())
        assert order_return.status.value == "rejected"
        assert event.reason == "not eligible"

    def test_approve_wrong_status_raises(self):
        order_return = self._return()
        order_return.reject("x", _now())
        with pytest.raises(InvalidReturnLifecycleTransition):
            order_return.approve(_now())

    def test_receive_before_approve_raises(self):
        order_return = self._return()
        with pytest.raises(InvalidReturnLifecycleTransition):
            order_return.receive(_now())

    def test_refund_before_receive_raises(self):
        order_return = self._return()
        order_return.approve(_now())
        with pytest.raises(InvalidReturnLifecycleTransition):
            order_return.refund(Money(amount=Decimal("10.00"), currency="UZS"), _now())

    def test_assert_within_window_passes(self):
        order_return = self._return()
        window = ReturnWindow(timedelta(days=14))
        order_return.assert_within_window(datetime(2026, 1, 1), datetime(2026, 1, 5), window)

    def test_assert_within_window_raises_when_expired(self):
        order_return = self._return()
        window = ReturnWindow(timedelta(days=14))
        with pytest.raises(ReturnWindowExpired):
            order_return.assert_within_window(datetime(2026, 1, 1), datetime(2026, 2, 1), window)

    def test_add_line(self):
        order_return = self._return()
        order_return.add_line(uuid.uuid4(), 2)
        assert len(order_return.lines) == 1


class TestOrderCancellationAggregate:
    def _cancellation(self) -> OrderCancellation:
        from apps.ordering.tests.factories import make_cancellation

        return make_cancellation()

    def test_approve_then_complete(self):
        cancellation = self._cancellation()
        cancellation.approve(_now())
        assert cancellation.status.value == "approved"
        event = cancellation.complete(Money(amount=Decimal("20.00"), currency="UZS"), _now())
        assert cancellation.status.value == "completed"
        assert event.cancellation_id == cancellation.id

    def test_reject_from_requested(self):
        cancellation = self._cancellation()
        event = cancellation.reject("cannot cancel", _now())
        assert cancellation.status.value == "rejected"
        assert event.reason == "cannot cancel"

    def test_approve_wrong_status_raises(self):
        cancellation = self._cancellation()
        cancellation.reject("x", _now())
        with pytest.raises(InvalidCancellationLifecycleTransition):
            cancellation.approve(_now())

    def test_complete_before_approve_raises(self):
        cancellation = self._cancellation()
        with pytest.raises(InvalidCancellationLifecycleTransition):
            cancellation.complete(None, _now())

    def test_complete_without_refund_amount(self):
        cancellation = self._cancellation()
        cancellation.approve(_now())
        cancellation.complete(None, _now())
        assert cancellation.refund_amount is None

    def test_add_line(self):
        cancellation = self._cancellation()
        cancellation.add_line(uuid.uuid4(), 1)
        assert len(cancellation.lines) == 1
