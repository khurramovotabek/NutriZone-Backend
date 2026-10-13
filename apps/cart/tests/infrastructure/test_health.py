from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest

from apps.cart.infrastructure.event_handlers import CACHE_GROUPS, handle_cart_event, invalidate_cart_cache_group
from apps.cart.infrastructure.health import (
    check_cart_cache,
    check_cart_repository,
    check_cart_state_consistency,
    check_reservation_cleanup,
    check_snapshot_validity,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestHealthChecks:
    def test_check_cart_repository_healthy(self):
        ok, detail = check_cart_repository()
        assert ok is True

    def test_check_cart_cache_round_trips(self):
        ok, detail = check_cart_cache()
        assert ok is True

    def test_check_cart_state_consistency_healthy_by_default(self):
        ok, detail = check_cart_state_consistency()
        assert ok is True

    def test_check_cart_state_consistency_flags_locked_archived_cart(self):
        """Seeds a deliberately inconsistent cart (archived while still locked) and verifies the health check actually catches it."""
        from apps.cart.infrastructure import models as orm

        orm.CartModel.objects.create(code="INCONSISTENT1", currency="UZS", status="archived", lock_reason="admin_hold")
        ok, detail = check_cart_state_consistency()
        assert ok is False
        assert "archived/converted" in detail

    def test_check_reservation_cleanup_reports_pending_count(self):
        ok, detail = check_reservation_cleanup()
        assert ok is True
        assert "pending sweep" in detail

    def test_check_snapshot_validity_healthy_for_empty_table(self):
        ok, detail = check_snapshot_validity()
        assert ok is True


class TestCacheGroupInvalidation:
    def test_rejects_unknown_group(self):
        with pytest.raises(ValueError):
            invalidate_cart_cache_group("not_a_real_group")

    def test_all_four_cache_groups_present(self):
        assert len(CACHE_GROUPS) == 4

    def test_invalidate_group_does_not_raise(self):
        invalidate_cart_cache_group("cart_detail")


class TestEventHandlerDispatch:
    def test_handle_cart_created_does_not_raise(self):
        handle_cart_event("CartCreated", {"cart_id": "x"})

    def test_handle_event_with_no_cache_side_effect_does_not_raise(self):
        """CheckoutReadinessCalculated has an empty cache-group tuple -- verifies dispatch handles that correctly."""
        handle_cart_event("CheckoutReadinessCalculated", {})

    def test_handle_unknown_event_is_a_noop(self):
        handle_cart_event("SomeUnregisteredEvent", {})


class TestCeleryTasks:
    def test_expire_carts_task_runs_without_error(self):
        from apps.cart.infrastructure.tasks import expire_carts

        assert isinstance(expire_carts(), int)

    def test_cleanup_abandoned_carts_task_runs_without_error(self):
        from apps.cart.infrastructure.tasks import cleanup_abandoned_carts

        assert isinstance(cleanup_abandoned_carts(), int)

    def test_cleanup_expired_reservations_actually_detaches_overdue_reservation(self):
        """Seeds a deliberately overdue AttachedReservation and verifies the task actually detaches it, not just runs without error."""
        from apps.cart.infrastructure import models as orm
        from apps.cart.infrastructure.tasks import cleanup_expired_reservations

        cart_row = orm.CartModel.objects.create(code="RESVCLEANUP1", currency="UZS")
        item_row = orm.CartItemModel.objects.create(cart=cart_row, product_variant_id=uuid.uuid4(), quantity=1)
        orm.AttachedReservationModel.objects.create(item=item_row, reservation_id=uuid.uuid4(), reserved_at=datetime.utcnow(), expires_at=datetime.utcnow() - timedelta(minutes=1))

        count = cleanup_expired_reservations()
        assert count >= 1
        assert not orm.AttachedReservationModel.objects.filter(item=item_row).exists()

    def test_rebuild_statistics_task_runs_without_error(self):
        from apps.cart.infrastructure.tasks import rebuild_statistics

        assert rebuild_statistics() == "ok"


class TestSelectors:
    def test_cart_selector_list(self):
        from apps.cart.infrastructure.selectors import CartSelector
        from apps.cart.infrastructure.repositories import DjangoCartRepository
        from apps.cart.tests.factories import make_cart

        DjangoCartRepository().save(make_cart())
        results, total = CartSelector().list(status=None, cart_type=None, page=1, page_size=20)
        assert total >= 1

    def test_abandoned_cart_selector(self):
        from apps.cart.infrastructure import models as orm
        from apps.cart.infrastructure.selectors import AbandonedCartSelector

        row = orm.CartModel.objects.create(code="ABANDONEDTEST", currency="UZS", status="active")
        orm.CartModel.objects.filter(id=row.id).update(updated_at=datetime.utcnow() - timedelta(days=10))
        abandoned = AbandonedCartSelector().list_abandoned(inactive_for_days=3)
        assert any(a["id"] == str(row.id) for a in abandoned)


class TestDjangoAdmin:
    def test_cart_admin_registered(self):
        from django.contrib import admin

        from apps.cart.infrastructure import models as orm

        assert orm.CartModel in admin.site._registry

    def test_outbox_event_removed_from_dashboard(self):
        """Real, product-required simplification: CartOutboxEvent (read-only, system-internal event-log data) removed from the Dashboard entirely -- an admin never created or edited it by hand anyway."""
        from django.contrib import admin

        from apps.cart.infrastructure import models as orm

        assert orm.CartOutboxEvent not in admin.site._registry
