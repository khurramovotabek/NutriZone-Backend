from __future__ import annotations

import dataclasses
import uuid

import pytest

from apps.cart.domain.events import (
    CartArchivedEvent,
    CartCreated,
    CartLockedEvent,
    CartMerged,
    CouponReferenceApplied,
    CustomerAssigned,
    ItemAdded,
    ItemQuantityUpdated,
    PriceSnapshotAttached,
)

pytestmark = pytest.mark.unit


def test_cart_created_payload():
    cart_id = uuid.uuid4()
    payload = CartCreated(cart_id=cart_id, cart_type="guest", source="web").to_payload()
    assert payload["cart_id"] == str(cart_id)
    assert payload["cart_type"] == "guest"


def test_item_added_payload():
    cart_id, item_id, variant_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    payload = ItemAdded(cart_id=cart_id, item_id=item_id, product_variant_id=variant_id, quantity=3).to_payload()
    assert payload["quantity"] == 3
    assert payload["product_variant_id"] == str(variant_id)


def test_item_quantity_updated_payload():
    payload = ItemQuantityUpdated(cart_id=uuid.uuid4(), item_id=uuid.uuid4(), old_quantity=2, new_quantity=5).to_payload()
    assert payload["old_quantity"] == 2
    assert payload["new_quantity"] == 5


def test_cart_merged_payload():
    target, source = uuid.uuid4(), uuid.uuid4()
    payload = CartMerged(target_cart_id=target, source_cart_id=source, items_merged=3, strategy="sum_quantities").to_payload()
    assert payload["target_cart_id"] == str(target)
    assert payload["source_cart_id"] == str(source)


def test_customer_assigned_payload():
    cart_id, customer_id = uuid.uuid4(), uuid.uuid4()
    payload = CustomerAssigned(cart_id=cart_id, customer_id=customer_id).to_payload()
    assert payload["customer_id"] == str(customer_id)


def test_coupon_reference_applied_payload():
    coupon_id = uuid.uuid4()
    payload = CouponReferenceApplied(cart_id=uuid.uuid4(), coupon_id=coupon_id).to_payload()
    assert payload["coupon_id"] == str(coupon_id)


def test_price_snapshot_attached_payload():
    item_id, snapshot_id = uuid.uuid4(), uuid.uuid4()
    payload = PriceSnapshotAttached(cart_id=uuid.uuid4(), item_id=item_id, price_snapshot_id=snapshot_id).to_payload()
    assert payload["item_id"] == str(item_id)
    assert payload["price_snapshot_id"] == str(snapshot_id)


def test_cart_archived_event_does_not_collide_with_exception_name():
    """CartArchivedEvent vs. the CartArchived domain exception -- verified both are importable simultaneously without conflict."""
    from apps.cart.domain.exceptions import CartArchived

    event = CartArchivedEvent(cart_id=uuid.uuid4())
    assert event.__class__.__name__ == "CartArchivedEvent"
    assert CartArchived.__name__ == "CartArchived"


def test_cart_locked_event_does_not_collide_with_exception_name():
    """CartLockedEvent vs. the CartLocked domain exception -- the near-miss caught during Phase 1 drafting, verified here to hold."""
    from apps.cart.domain.exceptions import CartLocked

    event = CartLockedEvent(cart_id=uuid.uuid4(), reason="admin_hold")
    assert event.__class__.__name__ == "CartLockedEvent"
    assert CartLocked.__name__ == "CartLocked"


def test_every_event_is_a_frozen_dataclass():
    import apps.cart.domain.events as events_module

    event_classes = [obj for name, obj in vars(events_module).items() if isinstance(obj, type) and dataclasses.is_dataclass(obj)]
    for cls in event_classes:
        params = cls.__dataclass_params__
        assert params.frozen is True, f"{cls.__name__} is not frozen"


def test_events_are_immutable():
    event = CartCreated(cart_id=uuid.uuid4(), cart_type="guest", source="web")
    with pytest.raises(Exception):
        event.cart_type = "authenticated"  # type: ignore[misc]


def test_self_validating_event_count():
    """
    Counts every event class directly from source via AST parsing --
    a self-validating check that fails loudly if a future change adds
    or removes an event without updating this test, per this phase's
    explicit request for exactly this kind of automatic count.
    """
    import ast

    import apps.cart.domain.events as events_module

    tree = ast.parse(open(events_module.__file__).read())
    class_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert len(class_names) == 22, f"Expected exactly 22 Cart domain events, found {len(class_names)}: {class_names}"
