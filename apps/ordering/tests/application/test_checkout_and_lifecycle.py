from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.ordering.application.services._shared import OrderingServiceContext
from apps.ordering.application.services.checkout import CompleteCheckout, CreateOrderFromCart
from apps.ordering.application.services.lifecycle import (
    ArchiveOrder, CancelOrder, CompleteOrder, ConfirmOrder, DeliverOrder, ExpireOrder, LoadOrder, LockOrder,
    RestoreOrder, ShipOrder, StartOrderProcessing, UnlockOrder,
)
from apps.ordering.domain.enums import OrderLockReason
from apps.ordering.tests.application.fakes import FakeOrderRepository, collect_events
from apps.ordering.tests.factories import make_confirmed_order, make_delivered_order, make_order_with_line
from common.exceptions import ResourceNotFound, ValidationFailed

pytestmark = pytest.mark.django_db  # every service uses @transaction.atomic -- same documented rationale as every prior module


def _ctx():
    events: list = []
    return OrderingServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestCreateOrderFromCart:
    def test_creates_order(self):
        repo = FakeOrderRepository()
        ctx, events = _ctx()
        order = CreateOrderFromCart(repo, ctx).execute(
            cart_id=uuid.uuid4(), customer_id=uuid.uuid4(), currency="UZS",
            shipping_address={"recipient_name": "Jane", "line1": "123 Main St", "city": "Tashkent", "country_code": "UZ"},
            billing_address={"recipient_name": "Jane", "line1": "123 Main St", "city": "Tashkent", "country_code": "UZ"},
            line_items=[{"product_variant_id": str(uuid.uuid4()), "quantity": 2, "unit_price": "50.00"}],
        )
        assert order.status.value == "pending_payment"
        assert any(e[0] == "OrderCreated" for e in events)

    def test_rejects_no_line_items(self):
        repo = FakeOrderRepository()
        ctx, _ = _ctx()
        with pytest.raises(ValidationFailed):
            CreateOrderFromCart(repo, ctx).execute(
                cart_id=None, customer_id=None, currency="UZS",
                shipping_address={"recipient_name": "Jane", "line1": "x", "city": "Tashkent", "country_code": "UZ"},
                billing_address={"recipient_name": "Jane", "line1": "x", "city": "Tashkent", "country_code": "UZ"},
                line_items=[],
            )


class TestCompleteCheckout:
    def test_confirms_order(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        ctx, events = _ctx()
        confirmed = CompleteCheckout(repo, ctx).execute(order.id)
        assert confirmed.status.value == "confirmed"
        assert any(e[0] == "OrderConfirmed" for e in events)


class TestLoadOrder:
    def test_load_by_id(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        assert LoadOrder(repo).execute(order_id=order.id).id == order.id

    def test_load_by_order_number(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        assert LoadOrder(repo).execute(order_number=order.order_number.value).id == order.id

    def test_load_missing_raises(self):
        with pytest.raises(ResourceNotFound):
            LoadOrder(FakeOrderRepository()).execute(order_id=uuid.uuid4())


class TestStatusTransitionServices:
    def test_confirm_order(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        ctx, events = _ctx()
        confirmed = ConfirmOrder(repo, ctx).execute(order.id)
        assert confirmed.status.value == "confirmed"
        assert any(e[0] == "OrderConfirmed" for e in events)

    def test_start_order_processing(self):
        repo = FakeOrderRepository()
        order = make_confirmed_order()
        repo.save(order)
        ctx, events = _ctx()
        processing = StartOrderProcessing(repo, ctx).execute(order.id)
        assert processing.status.value == "processing"
        assert any(e[0] == "OrderProcessingStarted" for e in events)

    def test_ship_order(self):
        from datetime import datetime as dt

        repo = FakeOrderRepository()
        order = make_confirmed_order()
        order.start_processing(dt.utcnow())
        repo.save(order)
        ctx, events = _ctx()
        shipped = ShipOrder(repo, ctx).execute(order.id)
        assert shipped.status.value == "shipped"
        assert any(e[0] == "OrderShipped" for e in events)

    def test_deliver_order(self):
        from datetime import datetime as dt

        repo = FakeOrderRepository()
        order = make_confirmed_order()
        order.start_processing(dt.utcnow())
        order.ship(dt.utcnow())
        repo.save(order)
        ctx, events = _ctx()
        delivered = DeliverOrder(repo, ctx).execute(order.id)
        assert delivered.status.value == "delivered"
        assert any(e[0] == "OrderDelivered" for e in events)

    def test_complete_order(self):
        repo = FakeOrderRepository()
        order = make_delivered_order()
        repo.save(order)
        ctx, events = _ctx()
        completed = CompleteOrder(repo, ctx).execute(order.id)
        assert completed.status.value == "completed"
        assert any(e[0] == "OrderCompleted" for e in events)

    def test_cancel_order(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        ctx, events = _ctx()
        cancelled = CancelOrder(repo, ctx).execute(order_id=order.id, reason="customer_request")
        assert cancelled.status.value == "cancelled"
        assert any(e[0] == "OrderCancelled" for e in events)

    def test_expire_order(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        ctx, events = _ctx()
        expired = ExpireOrder(repo, ctx).execute(order.id)
        assert expired.status.value == "failed"
        assert any(e[0] == "OrderFailedEvent" for e in events)


class TestLockUnlockArchiveRestoreServices:
    def test_lock_order(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        ctx, events = _ctx()
        locked = LockOrder(repo, ctx).execute(order_id=order.id, reason=OrderLockReason.FRAUD_REVIEW.value)
        assert locked.lock_reason == OrderLockReason.FRAUD_REVIEW
        assert any(e[0] == "OrderLockedEvent" for e in events)

    def test_unlock_order(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        order.lock(OrderLockReason.FRAUD_REVIEW)
        repo.save(order)
        ctx, events = _ctx()
        unlocked = UnlockOrder(repo, ctx).execute(order.id)
        assert unlocked.lock_reason is None
        assert any(e[0] == "OrderUnlocked" for e in events)

    def test_archive_order(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        ctx, events = _ctx()
        archived = ArchiveOrder(repo, ctx).execute(order.id)
        assert archived.is_archived is True
        assert any(e[0] == "OrderArchivedEvent" for e in events)

    def test_restore_order(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        order.archive()
        repo.save(order)
        ctx, events = _ctx()
        restored = RestoreOrder(repo, ctx).execute(order.id)
        assert restored.is_archived is False
        assert any(e[0] == "OrderRestored" for e in events)
