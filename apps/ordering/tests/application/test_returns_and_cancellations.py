from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.ordering.application.services._shared import OrderingServiceContext
from apps.ordering.application.services.cancellations import (
    ApproveCancellation, CompleteCancellation, GetCancellation, ListCancellationsForOrder, RejectCancellation, RequestCancellation,
)
from apps.ordering.application.services.returns import (
    ApproveReturn, GetReturn, ListReturnsForOrder, ReceiveReturn, RefundReturn, RejectReturn, RequestReturn,
)
from apps.ordering.tests.application.fakes import FakeOrderCancellationRepository, FakeOrderRepository, FakeOrderReturnRepository, collect_events
from apps.ordering.tests.factories import make_order_with_line
from common.exceptions import ResourceNotFound

pytestmark = pytest.mark.django_db


def _ctx():
    events: list = []
    return OrderingServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestReturnServices:
    def test_request_return(self):
        from apps.ordering.tests.factories import make_delivered_order

        order_repo = FakeOrderRepository()
        return_repo = FakeOrderReturnRepository()
        order = make_delivered_order()
        order_repo.save(order)
        line_id = next(iter(order.lines))
        ctx, events = _ctx()
        order_return = RequestReturn(return_repo, order_repo, ctx).execute(order_id=order.id, reason="defective", lines=[{"order_line_item_id": str(line_id), "quantity": 1}])
        assert order_return.status.value == "requested"
        assert any(e[0] == "ReturnRequested" for e in events)

    def test_request_return_missing_order_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            RequestReturn(FakeOrderReturnRepository(), FakeOrderRepository(), ctx).execute(order_id=uuid.uuid4(), reason="defective", lines=[])

    def test_full_return_lifecycle(self):
        repo = FakeOrderReturnRepository()
        from apps.ordering.tests.factories import make_return

        order_return = make_return()
        repo.save(order_return)
        ctx, events = _ctx()

        approved = ApproveReturn(repo, ctx).execute(order_return.id)
        assert approved.status.value == "approved"

        received = ReceiveReturn(repo, ctx).execute(order_return.id)
        assert received.status.value == "received"

        refunded = RefundReturn(repo, ctx).execute(return_id=order_return.id, amount=Decimal("25.00"), currency="UZS")
        assert refunded.status.value == "refunded"

        event_types = [e[0] for e in events]
        assert "ReturnApproved" in event_types
        assert "ReturnReceived" in event_types
        assert "ReturnRefunded" in event_types

    def test_reject_return(self):
        repo = FakeOrderReturnRepository()
        from apps.ordering.tests.factories import make_return

        order_return = make_return()
        repo.save(order_return)
        ctx, events = _ctx()
        rejected = RejectReturn(repo, ctx).execute(return_id=order_return.id, reason="not eligible")
        assert rejected.status.value == "rejected"
        assert any(e[0] == "ReturnRejected" for e in events)

    def test_get_return(self):
        repo = FakeOrderReturnRepository()
        from apps.ordering.tests.factories import make_return

        order_return = make_return()
        repo.save(order_return)
        assert GetReturn(repo).execute(order_return.id).id == order_return.id

    def test_get_return_missing_raises(self):
        with pytest.raises(ResourceNotFound):
            GetReturn(FakeOrderReturnRepository()).execute(uuid.uuid4())

    def test_list_returns_for_order(self):
        repo = FakeOrderReturnRepository()
        from apps.ordering.tests.factories import make_return

        order_id = uuid.uuid4()
        repo.save(make_return(order_id=order_id))
        results = ListReturnsForOrder(repo).execute(order_id)
        assert len(results) == 1


class TestCancellationServices:
    def test_request_cancellation(self):
        order_repo = FakeOrderRepository()
        cancellation_repo = FakeOrderCancellationRepository()
        order = make_order_with_line()
        order_repo.save(order)
        line_id = next(iter(order.lines))
        ctx, events = _ctx()
        cancellation = RequestCancellation(cancellation_repo, order_repo, ctx).execute(order_id=order.id, reason="customer_request", lines=[{"order_line_item_id": str(line_id), "quantity": 1}])
        assert cancellation.status.value == "requested"
        assert any(e[0] == "CancellationRequested" for e in events)

    def test_full_cancellation_lifecycle(self):
        repo = FakeOrderCancellationRepository()
        from apps.ordering.tests.factories import make_cancellation

        cancellation = make_cancellation()
        repo.save(cancellation)
        ctx, events = _ctx()

        approved = ApproveCancellation(repo, ctx).execute(cancellation.id)
        assert approved.status.value == "approved"

        completed = CompleteCancellation(repo, ctx).execute(cancellation_id=cancellation.id, refund_amount=Decimal("10.00"), currency="UZS")
        assert completed.status.value == "completed"

        event_types = [e[0] for e in events]
        assert "CancellationApproved" in event_types
        assert "CancellationCompleted" in event_types

    def test_reject_cancellation(self):
        repo = FakeOrderCancellationRepository()
        from apps.ordering.tests.factories import make_cancellation

        cancellation = make_cancellation()
        repo.save(cancellation)
        ctx, events = _ctx()
        rejected = RejectCancellation(repo, ctx).execute(cancellation_id=cancellation.id, reason="cannot cancel")
        assert rejected.status.value == "rejected"
        assert any(e[0] == "CancellationRejected" for e in events)

    def test_get_cancellation(self):
        repo = FakeOrderCancellationRepository()
        from apps.ordering.tests.factories import make_cancellation

        cancellation = make_cancellation()
        repo.save(cancellation)
        assert GetCancellation(repo).execute(cancellation.id).id == cancellation.id

    def test_list_cancellations_for_order(self):
        repo = FakeOrderCancellationRepository()
        from apps.ordering.tests.factories import make_cancellation

        order_id = uuid.uuid4()
        repo.save(make_cancellation(order_id=order_id))
        results = ListCancellationsForOrder(repo).execute(order_id)
        assert len(results) == 1
