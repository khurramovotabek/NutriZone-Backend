from __future__ import annotations

import uuid

import pytest

from apps.ordering.application.services._shared import OrderingServiceContext
from apps.ordering.application.services.invoicing import IssueInvoice
from apps.ordering.application.services.queries import AdminListOrders, GetOrderSummary, ListCustomerOrders, SearchOrders
from apps.ordering.domain.enums import OrderChannel
from apps.ordering.tests.application.fakes import FakeOrderRepository, FakeOrderSearchGateway, collect_events
from apps.ordering.tests.factories import make_order_with_line
from common.exceptions import ResourceNotFound

pytestmark = pytest.mark.django_db


def _ctx():
    events: list = []
    return OrderingServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestIssueInvoice:
    def test_issues_invoice(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        ctx, events = _ctx()
        updated = IssueInvoice(repo, ctx).execute(order_id=order.id, sequence=1)
        assert updated.invoice.status.value == "issued"
        assert any(e[0] == "InvoiceIssued" for e in events)

    def test_issue_invoice_twice_raises(self):
        repo = FakeOrderRepository()
        order = make_order_with_line()
        repo.save(order)
        ctx, _ = _ctx()
        IssueInvoice(repo, ctx).execute(order_id=order.id, sequence=1)
        with pytest.raises(Exception):
            IssueInvoice(repo, ctx).execute(order_id=order.id, sequence=2)


class TestQueries:
    def test_admin_list_orders(self):
        repo = FakeOrderRepository()
        repo.save(make_order_with_line())
        results, total = AdminListOrders(repo).execute()
        assert total == 1

    def test_list_customer_orders(self):
        repo = FakeOrderRepository()
        customer_id = uuid.uuid4()
        repo.save(make_order_with_line(customer_id=customer_id))
        results, total = ListCustomerOrders(repo).execute(customer_id)
        assert total == 1

    def test_search_orders(self):
        gateway = FakeOrderSearchGateway(results=[{"order_number": "ORD-TEST0001"}])
        results, total = SearchOrders(gateway).execute("ORD-TEST", {})
        assert total == 1

    def test_get_order_summary(self):
        class _FakeReadRepo:
            def get_summary(self, order_id):
                return {"id": str(order_id), "status": "confirmed"}

        summary = GetOrderSummary(_FakeReadRepo()).execute(uuid.uuid4())
        assert summary["status"] == "confirmed"

    def test_get_order_summary_missing_raises(self):
        class _FakeReadRepo:
            def get_summary(self, order_id):
                return None

        with pytest.raises(ResourceNotFound):
            GetOrderSummary(_FakeReadRepo()).execute(uuid.uuid4())
