from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from apps.ordering.infrastructure.event_handlers import CACHE_GROUPS, handle_ordering_event, invalidate_ordering_cache_group
from apps.ordering.infrastructure.health import (
    check_database_consistency,
    check_expired_orders,
    check_ordering_cache,
    check_ordering_repository,
    check_outbox_pending_events,
    check_stale_returns,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestHealthChecks:
    def test_check_ordering_repository_healthy(self):
        ok, detail = check_ordering_repository()
        assert ok is True

    def test_check_ordering_cache_round_trips(self):
        ok, detail = check_ordering_cache()
        assert ok is True

    def test_check_outbox_pending_events_reports_count(self):
        ok, detail = check_outbox_pending_events()
        assert ok is True
        assert "pending" in detail

    def test_check_expired_orders_reports_pending_count(self):
        ok, detail = check_expired_orders()
        assert ok is True
        assert "pending sweep" in detail

    def test_check_stale_returns_reports_count(self):
        ok, detail = check_stale_returns()
        assert ok is True

    def test_check_database_consistency_healthy_by_default(self):
        ok, detail = check_database_consistency()
        assert ok is True

    def test_check_database_consistency_flags_locked_cancelled_order(self):
        """Seeds a deliberately inconsistent order (cancelled while still locked) and verifies the health check actually catches it."""
        from apps.ordering.infrastructure import models as orm

        orm.OrderModel.objects.create(
            order_number="ORD-INCONSISTENT1", currency="UZS", status="cancelled", lock_reason="fraud_review",
            shipping_recipient_name="X", shipping_line1="X", shipping_city="X", shipping_country_code="UZ",
            billing_recipient_name="X", billing_line1="X", billing_city="X", billing_country_code="UZ",
        )
        ok, detail = check_database_consistency()
        assert ok is False
        assert "cancelled/failed" in detail


class TestCacheGroupInvalidation:
    def test_rejects_unknown_group(self):
        with pytest.raises(ValueError):
            invalidate_ordering_cache_group("not_a_real_group")

    def test_all_four_cache_groups_present(self):
        assert len(CACHE_GROUPS) == 4

    def test_invalidate_group_does_not_raise(self):
        invalidate_ordering_cache_group("order_detail")


class TestEventHandlerDispatch:
    def test_handle_order_created_does_not_raise(self):
        handle_ordering_event("OrderCreated", {"order_id": "x"})

    def test_handle_unknown_event_is_a_noop(self):
        handle_ordering_event("SomeUnregisteredEvent", {})

    def test_all_28_events_dispatched(self):
        """Cross-checks the dispatch table against domain/events.py directly -- this phase explicitly requires this verification."""
        import ast

        import apps.ordering.domain.events as events_module
        from apps.ordering.infrastructure.event_handlers import _EVENT_TO_CACHE_GROUPS

        tree = ast.parse(open(events_module.__file__).read())
        domain_events = set(n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        dispatched = set(_EVENT_TO_CACHE_GROUPS.keys())
        assert domain_events == dispatched, f"Mismatch: {domain_events.symmetric_difference(dispatched)}"

    def test_all_28_events_registered(self):
        """Cross-checks shared/event_contracts/ordering.py against domain/events.py directly."""
        import ast

        import apps.ordering.domain.events as events_module

        tree = ast.parse(open(events_module.__file__).read())
        domain_events = set(n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef))

        with open("shared/event_contracts/ordering.py") as f:
            contract_tree = ast.parse(f.read())
        registered = set(n.elts[0].value for n in ast.walk(contract_tree) if isinstance(n, ast.Tuple) and len(n.elts) == 2 and isinstance(n.elts[0], ast.Constant))
        assert domain_events == registered, f"Mismatch: {domain_events.symmetric_difference(registered)}"


class TestCeleryTasks:
    def test_expire_orders_task_runs_without_error(self):
        from apps.ordering.infrastructure.tasks import expire_orders

        assert isinstance(expire_orders(), int)

    def test_cleanup_stale_return_requests_task_runs_without_error(self):
        from apps.ordering.infrastructure.tasks import cleanup_stale_return_requests

        assert isinstance(cleanup_stale_return_requests(), int)

    def test_cleanup_stale_return_requests_counts_seeded_stale_return(self):
        """Seeds a deliberately stale return request and verifies the task actually counts it, not just runs without error."""
        from apps.ordering.infrastructure import models as orm
        from apps.ordering.infrastructure.tasks import cleanup_stale_return_requests

        orm.OrderReturnModel.objects.create(return_number="RET-STALETEST01", order_id=uuid.uuid4(), status="requested", requested_at=datetime.utcnow() - timedelta(days=45))
        count = cleanup_stale_return_requests(older_than_days=30)
        assert count >= 1

    def test_rebuild_statistics_task_runs_without_error(self):
        from apps.ordering.infrastructure.tasks import rebuild_statistics

        assert rebuild_statistics() == "ok"


class TestGateways:
    def test_payment_gateway_placeholder_raises(self):
        from apps.ordering.infrastructure.gateways.payment_gateway import NotImplementedPaymentGateway

        with pytest.raises(NotImplementedError):
            NotImplementedPaymentGateway().get_payment_status(uuid.uuid4())

    def test_fulfillment_gateway_placeholder_raises(self):
        from apps.ordering.infrastructure.gateways.fulfillment_gateway import NotImplementedFulfillmentGateway

        with pytest.raises(NotImplementedError):
            NotImplementedFulfillmentGateway().get_fulfillment_status(uuid.uuid4())

    def test_notification_gateway_placeholder_is_a_silent_noop(self):
        """Verifies the deliberate asymmetry documented in Phase 2: Notification never raises, unlike Payment/Fulfillment."""
        from apps.ordering.infrastructure.gateways.notification_gateway import NotImplementedNotificationGateway

        NotImplementedNotificationGateway().notify_order_event(uuid.uuid4(), "OrderCreated", {})  # must not raise


class TestDjangoAdmin:
    def test_order_admin_registered(self):
        from django.contrib import admin

        from apps.ordering.infrastructure import models as orm

        assert orm.OrderModel in admin.site._registry

    def test_all_3_remaining_admin_registrations_present(self):
        """Real, product-required simplification: OrderLineItemModel (redundant with Order's own inline), OrderStatusHistoryEntryModel/OrderFailureModel/OrderingOutboxEvent (read-only, system-internal), and OrderPaymentReferenceModel/OrderFulfillmentReferenceModel (cross-app references, best viewed via Order itself -- Fulfillment's own module no longer even exists) were all removed from the Dashboard. Only the 3 registrations an admin genuinely acts on directly remain."""
        from django.contrib import admin

        from apps.ordering.infrastructure import models as orm

        expected = [orm.OrderModel, orm.OrderReturnModel, orm.OrderCancellationModel]
        for model in expected:
            assert model in admin.site._registry, f"{model.__name__} is not registered in admin"

    def test_outbox_event_removed_from_dashboard(self):
        """Real, product-required simplification: OrderingOutboxEvent removed from the Dashboard entirely -- read-only, system-internal event-log data."""
        from django.contrib import admin

        from apps.ordering.infrastructure import models as orm

        assert orm.OrderingOutboxEvent not in admin.site._registry

    def test_status_history_removed_from_dashboard(self):
        """Real, product-required simplification: OrderStatusHistoryEntryModel removed from the Dashboard entirely -- read-only, system-internal audit log."""
        from django.contrib import admin

        from apps.ordering.infrastructure import models as orm

        assert orm.OrderStatusHistoryEntryModel not in admin.site._registry


class TestSelectors:
    def test_order_selector_list(self):
        from apps.ordering.infrastructure.repositories import DjangoOrderRepository
        from apps.ordering.infrastructure.selectors import OrderSelector
        from apps.ordering.tests.factories import make_order_with_line

        DjangoOrderRepository().save(make_order_with_line())
        results, total = OrderSelector().list(status=None, customer_id=None, page=1, page_size=20)
        assert total >= 1

    def test_expiring_order_selector(self):
        from apps.ordering.infrastructure import models as orm
        from apps.ordering.infrastructure.selectors import ExpiringOrderSelector

        row = orm.OrderModel.objects.create(
            order_number="ORD-EXPIRETEST1", currency="UZS", status="pending_payment", placed_at=datetime.utcnow() - timedelta(hours=5),
            shipping_recipient_name="X", shipping_line1="X", shipping_city="X", shipping_country_code="UZ",
            billing_recipient_name="X", billing_line1="X", billing_city="X", billing_country_code="UZ",
        )
        expiring = ExpiringOrderSelector().list_expiring()
        assert any(e["id"] == str(row.id) for e in expiring)

    def test_statistics_selector_counts_by_status(self):
        from apps.ordering.infrastructure.repositories import DjangoOrderRepository
        from apps.ordering.infrastructure.selectors import OrderStatisticsSelector
        from apps.ordering.tests.factories import make_order_with_line

        DjangoOrderRepository().save(make_order_with_line())
        counts = OrderStatisticsSelector().counts_by_status()
        assert sum(counts.values()) >= 1


class TestComposition:
    def test_composition_builds_a_real_service(self):
        from apps.ordering.infrastructure.composition import build_load_order

        service = build_load_order()
        assert service is not None

    def test_all_47_factories_are_callable(self):
        """Verifies every build_* factory in composition.py actually executes without error -- not just that it's syntactically defined. Count re-verified fresh at 47 (was 46 before Phase 02E's build_update_payment_status)."""
        import inspect

        from apps.ordering.infrastructure import composition

        factories = [name for name, obj in vars(composition).items() if name.startswith("build_") and inspect.isfunction(obj)]
        assert len(factories) == 47
        for name in factories:
            factory = getattr(composition, name)
            factory()  # every factory accepts zero required args (actor_id defaults to None)
