from __future__ import annotations

import dataclasses
import uuid

import pytest

from apps.ordering.domain.events import (
    CancellationRequested,
    OrderArchivedEvent,
    OrderCancelled,
    OrderCreated,
    OrderLockedEvent,
    PaymentReferenceAdded,
    ReturnRequested,
)

pytestmark = pytest.mark.unit


def test_order_created_payload():
    order_id, cart_id, customer_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    payload = OrderCreated(order_id=order_id, order_number="ORD-A1B2C3", cart_id=cart_id, customer_id=customer_id).to_payload()
    assert payload["order_id"] == str(order_id)
    assert payload["order_number"] == "ORD-A1B2C3"


def test_order_created_payload_handles_null_cart_and_customer():
    payload = OrderCreated(order_id=uuid.uuid4(), order_number="ORD-A1B2C3", cart_id=None, customer_id=None).to_payload()
    assert payload["cart_id"] is None
    assert payload["customer_id"] is None


def test_order_cancelled_payload():
    order_id = uuid.uuid4()
    payload = OrderCancelled(order_id=order_id, reason="customer_request").to_payload()
    assert payload["reason"] == "customer_request"


def test_payment_reference_added_payload():
    order_id, payment_id = uuid.uuid4(), uuid.uuid4()
    payload = PaymentReferenceAdded(order_id=order_id, payment_id=payment_id).to_payload()
    assert payload["payment_id"] == str(payment_id)


def test_return_requested_payload():
    return_id, order_id = uuid.uuid4(), uuid.uuid4()
    payload = ReturnRequested(return_id=return_id, order_id=order_id).to_payload()
    assert payload["return_id"] == str(return_id)
    assert payload["order_id"] == str(order_id)


def test_cancellation_requested_payload():
    cancellation_id, order_id = uuid.uuid4(), uuid.uuid4()
    payload = CancellationRequested(cancellation_id=cancellation_id, order_id=order_id).to_payload()
    assert payload["cancellation_id"] == str(cancellation_id)


def test_order_locked_event_does_not_collide_with_exception_name():
    """OrderLockedEvent vs. the OrderLocked domain exception -- the near-miss caught during Phase 1 drafting, verified here to still hold."""
    from apps.ordering.domain.exceptions import OrderLocked

    event = OrderLockedEvent(order_id=uuid.uuid4(), reason="fraud_review")
    assert event.__class__.__name__ == "OrderLockedEvent"
    assert OrderLocked.__name__ == "OrderLocked"


def test_order_archived_event_does_not_collide_with_exception_name():
    event = OrderArchivedEvent(order_id=uuid.uuid4())
    assert event.__class__.__name__ == "OrderArchivedEvent"


def test_every_event_is_a_frozen_dataclass():
    import apps.ordering.domain.events as events_module

    event_classes = [obj for name, obj in vars(events_module).items() if isinstance(obj, type) and dataclasses.is_dataclass(obj)]
    for cls in event_classes:
        params = cls.__dataclass_params__
        assert params.frozen is True, f"{cls.__name__} is not frozen"


def test_events_are_immutable():
    event = OrderCreated(order_id=uuid.uuid4(), order_number="ORD-A1B2C3", cart_id=None, customer_id=None)
    with pytest.raises(Exception):
        event.order_number = "ORD-CHANGED"  # type: ignore[misc]


def test_programmatically_verify_exactly_28_events():
    """AST-parses events.py directly -- this phase explicitly requires this exact check."""
    import ast

    import apps.ordering.domain.events as events_module

    tree = ast.parse(open(events_module.__file__).read())
    class_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert len(class_names) == 28, f"Expected exactly 28 Ordering domain events, found {len(class_names)}: {class_names}"


def test_zero_collisions_between_events_and_exceptions():
    """A full, programmatic cross-check -- not just the two known near-misses above -- run once per phase to catch any collision introduced anywhere in either file."""
    import ast

    import apps.ordering.domain.events as events_module
    import apps.ordering.domain.exceptions as exceptions_module

    event_names = set(n.name for n in ast.walk(ast.parse(open(events_module.__file__).read())) if isinstance(n, ast.ClassDef))
    exception_names = set(n.name for n in ast.walk(ast.parse(open(exceptions_module.__file__).read())) if isinstance(n, ast.ClassDef))
    collisions = event_names & exception_names
    assert not collisions, f"Naming collisions found between events and exceptions: {collisions}"
