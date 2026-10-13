from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.pricing.infrastructure.event_handlers import CACHE_GROUPS, handle_pricing_event, invalidate_pricing_cache_group
from apps.pricing.infrastructure.health import (
    check_pricing_cache,
    check_pricing_calculation_engine,
    check_pricing_campaigns,
    check_pricing_repository,
    check_pricing_snapshots,
)

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestHealthChecks:
    def test_check_pricing_repository_healthy(self):
        ok, detail = check_pricing_repository()
        assert ok is True

    def test_check_pricing_cache_round_trips(self):
        ok, detail = check_pricing_cache()
        assert ok is True

    def test_check_pricing_calculation_engine_produces_correct_result(self):
        """The most important health check in this module -- actually runs PriceCalculationEngine and verifies the numeric result, not just that the import succeeds."""
        ok, detail = check_pricing_calculation_engine()
        assert ok is True
        assert detail == "ok"

    def test_check_pricing_snapshots_reports_pending_count(self):
        ok, detail = check_pricing_snapshots()
        assert ok is True
        assert "pending sweep" in detail

    def test_check_pricing_campaigns_flags_overdue_active_campaigns(self):
        from apps.pricing.infrastructure import models as orm

        orm.CampaignModel.objects.create(
            campaign_type="campaign", name="Overdue Campaign", status="active", discount_value_type="percentage", discount_percentage=Decimal("10"),
            validity_starts_at="2020-01-01T00:00:00Z", validity_ends_at="2020-01-02T00:00:00Z",
        )
        ok, detail = check_pricing_campaigns()
        assert ok is False
        assert "past their end date" in detail


class TestCacheGroupInvalidation:
    def test_rejects_unknown_group(self):
        with pytest.raises(ValueError):
            invalidate_pricing_cache_group("not_a_real_group")

    def test_all_six_cache_groups_present(self):
        assert len(CACHE_GROUPS) == 6

    def test_invalidate_group_does_not_raise(self):
        invalidate_pricing_cache_group("price_list_detail")


class TestEventHandlerDispatch:
    def test_handle_price_list_created_does_not_raise(self):
        handle_pricing_event("PriceListCreated", {"price_list_id": "x"})

    def test_handle_event_with_no_cache_side_effect_does_not_raise(self):
        """PriceLocked has an empty cache-group tuple -- verifies dispatch handles that correctly rather than erroring."""
        handle_pricing_event("PriceLocked", {})

    def test_handle_unknown_event_is_a_noop(self):
        handle_pricing_event("SomeUnregisteredEvent", {})


class TestCeleryTasks:
    def test_expire_campaigns_task_runs_without_error(self):
        from apps.pricing.infrastructure.tasks import expire_campaigns

        result = expire_campaigns()
        assert isinstance(result, int)

    def test_expire_coupons_task_runs_without_error(self):
        from apps.pricing.infrastructure.tasks import expire_coupons

        result = expire_coupons()
        assert isinstance(result, int)

    def test_expire_price_snapshots_task_runs_without_error(self):
        from apps.pricing.infrastructure.tasks import expire_price_snapshots

        result = expire_price_snapshots()
        assert isinstance(result, int)

    def test_expire_price_snapshots_actually_expires_overdue_locked_snapshot(self):
        """Seeds a deliberately overdue LOCKED snapshot and verifies the task actually transitions it, not just that it runs without error."""
        from apps.pricing.infrastructure import models as orm
        from apps.pricing.infrastructure.tasks import expire_price_snapshots

        row = orm.PriceSnapshotModel.objects.create(product_variant_id=uuid.uuid4(), locked_price_amount=Decimal("10.00"), currency="UZS", expires_at="2020-01-01T00:00:00Z", status="locked")
        count = expire_price_snapshots()
        assert count >= 1
        row.refresh_from_db()
        assert row.status == "expired"

    def test_activate_scheduled_campaigns_task_runs_without_error(self):
        from apps.pricing.infrastructure.tasks import activate_scheduled_campaigns

        result = activate_scheduled_campaigns()
        assert isinstance(result, int)

    def test_rebuild_statistics_task_runs_without_error(self):
        from apps.pricing.infrastructure.tasks import rebuild_statistics

        assert rebuild_statistics() == "ok"


class TestDjangoAdmin:
    def test_price_list_admin_removed_from_dashboard(self):
        """Real, product-required simplification: the raw Price List container CRUD removed from the Dashboard -- the friendlier Price List dashboard page (apps.products.infrastructure.price_list_view) covers the real per-variant Base/Old/Price task instead, now with a real Stock column too."""
        from django.contrib import admin

        from apps.pricing.infrastructure import models as orm

        assert orm.PriceListModel not in admin.site._registry

    def test_pricing_rule_admin_removed_from_dashboard(self):
        """Real, product-required simplification: "Price Rules" removed from the Dashboard's visible admin surface -- the one real, day-to-day pricing task (Base/Old/Price per variant) stays fully available via the Price List dashboard page and Product Edit's own Pricing section."""
        from django.contrib import admin

        from apps.pricing.infrastructure import models as orm

        assert orm.PricingRuleModel not in admin.site._registry

    def test_coupon_admin_registered(self):
        from django.contrib import admin

        from apps.pricing.infrastructure import models as orm

        assert orm.CouponModel in admin.site._registry

    def test_outbox_event_removed_from_dashboard(self):
        """Real, product-required simplification: PricingOutboxEvent removed from the Dashboard entirely -- read-only, system-internal event-log data."""
        from django.contrib import admin

        from apps.pricing.infrastructure import models as orm

        assert orm.PricingOutboxEvent not in admin.site._registry
