from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from apps.ordering.application.services._shared import OrderingServiceContext
from apps.ordering.application.services.references import (
    AttachCoupon, AttachPaymentReference, AttachPriceSnapshot, AttachReservation, AttachShipment, UpdateAddress,
)
from apps.ordering.tests.application.fakes import FakeOrderRepository, collect_events
from apps.ordering.tests.factories import make_address, make_confirmed_order, make_order_with_line
from common.exceptions import ResourceNotFound

pytestmark = pytest.mark.django_db


def _ctx():
    events: list = []
    return OrderingServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestReferenceServices:
    def test_attach_shipment(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        ctx, events = _ctx()
        fulfillment_id = uuid.uuid4()
        updated = AttachShipment(repo, ctx).execute(order_id=order.id, fulfillment_id=fulfillment_id)
        assert len(updated.fulfillment_references) == 1
        assert any(e[0] == "FulfillmentReferenceAdded" for e in events)

    def test_attach_payment_reference(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        ctx, events = _ctx()
        updated = AttachPaymentReference(repo, ctx).execute(order_id=order.id, payment_id=uuid.uuid4(), amount=Decimal("100.00"))
        assert len(updated.payment_references) == 1
        assert any(e[0] == "PaymentReferenceAdded" for e in events)

    def test_attach_reservation(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        line_id = next(iter(order.lines))
        ctx, _ = _ctx()
        reservation_id = uuid.uuid4()
        updated = AttachReservation(repo, ctx).execute(order_id=order.id, line_item_id=line_id, reservation_id=reservation_id)
        assert updated.lines[line_id].reservation_id == reservation_id

    def test_attach_price_snapshot(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        line_id = next(iter(order.lines))
        ctx, _ = _ctx()
        snapshot_id = uuid.uuid4()
        updated = AttachPriceSnapshot(repo, ctx).execute(order_id=order.id, line_item_id=line_id, price_snapshot_id=snapshot_id)
        assert updated.lines[line_id].price_snapshot_id == snapshot_id

    def test_attach_coupon(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        ctx, _ = _ctx()
        coupon_id = uuid.uuid4()
        updated = AttachCoupon(repo, ctx).execute(order_id=order.id, coupon_id=coupon_id)
        assert coupon_id in updated.coupon_ids

    def test_attach_coupon_on_confirmed_order_raises(self):
        """Verifies the Application Service correctly surfaces the domain's OrderNotModifiable rule -- not just that the happy path works."""
        from apps.ordering.domain.exceptions import OrderNotModifiable

        repo = FakeOrderRepository()
        order = make_confirmed_order()
        repo.save(order)
        ctx, _ = _ctx()
        with pytest.raises(OrderNotModifiable):
            AttachCoupon(repo, ctx).execute(order_id=order.id, coupon_id=uuid.uuid4())

    def test_update_address(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        ctx, _ = _ctx()
        updated = UpdateAddress(repo, ctx).execute(order_id=order.id, shipping_address={"recipient_name": "Jane", "line1": "456 Oak Ave", "city": "Samarkand", "country_code": "UZ"})
        assert updated.shipping_address.city == "Samarkand"

    def test_missing_order_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            AttachShipment(FakeOrderRepository(), ctx).execute(order_id=uuid.uuid4(), fulfillment_id=uuid.uuid4())
