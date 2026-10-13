from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from apps.cart.application.services._shared import CartServiceContext
from apps.cart.application.services.items import AddItem, BulkUpdateItems, ClearCart, RemoveItem, UpdateQuantity
from apps.cart.application.services.references import (
    ApplyCouponReference, AttachPriceSnapshot, AttachReservation, DetachPriceSnapshot, DetachReservation, RemoveCouponReference,
)
from apps.cart.tests.application.fakes import FakeCartRepository, collect_events
from apps.cart.tests.factories import make_cart
from common.exceptions import ResourceNotFound

pytestmark = pytest.mark.django_db


def _ctx():
    events: list = []
    return CartServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestItemServices:
    def test_add_item(self):
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        ctx, events = _ctx()
        updated = AddItem(repo, ctx).execute(cart_id=cart.id, product_variant_id=uuid.uuid4(), quantity=2)
        assert len(updated.items) == 1
        assert any(e[0] == "ItemAdded" for e in events)

    def test_add_item_exceeding_max_raises(self):
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        ctx, _ = _ctx()
        with pytest.raises(Exception):
            AddItem(repo, ctx).execute(cart_id=cart.id, product_variant_id=uuid.uuid4(), quantity=99999)

    def test_remove_item(self):
        repo = FakeCartRepository()
        cart = make_cart()
        added_event = cart.add_item(uuid.uuid4(), 1, datetime.utcnow())
        repo.save(cart)
        ctx, events = _ctx()
        RemoveItem(repo, ctx).execute(cart_id=cart.id, item_id=added_event.item_id)
        assert any(e[0] == "ItemRemoved" for e in events)

    def test_update_quantity(self):
        repo = FakeCartRepository()
        cart = make_cart()
        added_event = cart.add_item(uuid.uuid4(), 1, datetime.utcnow())
        repo.save(cart)
        ctx, events = _ctx()
        updated = UpdateQuantity(repo, ctx).execute(cart_id=cart.id, item_id=added_event.item_id, quantity=5)
        assert updated.items[added_event.item_id].quantity.value == 5
        assert any(e[0] == "ItemQuantityUpdated" for e in events)

    def test_bulk_update_items(self):
        repo = FakeCartRepository()
        cart = make_cart()
        now = datetime.utcnow()
        a = cart.add_item(uuid.uuid4(), 1, now)
        b = cart.add_item(uuid.uuid4(), 1, now)
        repo.save(cart)
        ctx, events = _ctx()
        updated = BulkUpdateItems(repo, ctx).execute(cart_id=cart.id, updates={a.item_id: 3, b.item_id: 4})
        assert updated.items[a.item_id].quantity.value == 3
        assert len([e for e in events if e[0] == "ItemQuantityUpdated"]) == 2

    def test_clear_cart(self):
        repo = FakeCartRepository()
        cart = make_cart()
        cart.add_item(uuid.uuid4(), 1, datetime.utcnow())
        repo.save(cart)
        ctx, events = _ctx()
        cleared = ClearCart(repo, ctx).execute(cart.id)
        assert all(i.status.value == "removed" for i in cleared.items.values())
        assert any(e[0] == "CartCleared" for e in events)

    def test_missing_cart_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            AddItem(FakeCartRepository(), ctx).execute(cart_id=uuid.uuid4(), product_variant_id=uuid.uuid4(), quantity=1)


class TestReferenceServices:
    def test_apply_and_remove_coupon(self):
        repo = FakeCartRepository()
        cart = make_cart()
        repo.save(cart)
        ctx, events = _ctx()
        coupon_id = uuid.uuid4()

        updated = ApplyCouponReference(repo, ctx).execute(cart_id=cart.id, coupon_id=coupon_id)
        assert coupon_id in updated.coupon_ids

        updated = RemoveCouponReference(repo, ctx).execute(cart_id=cart.id, coupon_id=coupon_id)
        assert coupon_id not in updated.coupon_ids
        event_types = [e[0] for e in events]
        assert "CouponReferenceApplied" in event_types
        assert "CouponReferenceRemoved" in event_types

    def test_attach_and_detach_price_snapshot(self):
        repo = FakeCartRepository()
        cart = make_cart()
        added_event = cart.add_item(uuid.uuid4(), 1, datetime.utcnow())
        repo.save(cart)
        ctx, events = _ctx()

        updated = AttachPriceSnapshot(repo, ctx).execute(cart_id=cart.id, item_id=added_event.item_id, price_snapshot_id=uuid.uuid4(), unit_amount=Decimal("10.00"), currency="UZS")
        assert updated.items[added_event.item_id].price_reference is not None

        updated = DetachPriceSnapshot(repo, ctx).execute(cart_id=cart.id, item_id=added_event.item_id)
        assert updated.items[added_event.item_id].price_reference is None
        event_types = [e[0] for e in events]
        assert "PriceSnapshotAttached" in event_types
        assert "PriceSnapshotDetached" in event_types

    def test_attach_and_detach_reservation(self):
        repo = FakeCartRepository()
        cart = make_cart()
        added_event = cart.add_item(uuid.uuid4(), 1, datetime.utcnow())
        repo.save(cart)
        ctx, events = _ctx()
        reservation_id = uuid.uuid4()

        updated = AttachReservation(repo, ctx).execute(cart_id=cart.id, item_id=added_event.item_id, reservation_id=reservation_id)
        assert updated.items[added_event.item_id].reservation_reference.reservation_id == reservation_id

        updated = DetachReservation(repo, ctx).execute(cart_id=cart.id, item_id=added_event.item_id)
        assert updated.items[added_event.item_id].reservation_reference is None
        event_types = [e[0] for e in events]
        assert "ReservationAttached" in event_types
        assert "ReservationDetached" in event_types
