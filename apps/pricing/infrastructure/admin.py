"""
Django Admin registration -- engineering/ops debugging tool only, per
Django Implementation Blueprint §13 and MIC §9's Admin Contract. Bulk
actions call Application Services exclusively.
"""
from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

from apps.pricing.application.services._shared import PricingServiceContext
from apps.pricing.application.services.price_lists import ArchivePriceList
from apps.pricing.application.services.rules_and_campaigns import EndCampaign
from apps.pricing.infrastructure import models as orm
from apps.pricing.infrastructure.repositories import (
    DjangoCampaignRepository,
    DjangoPriceListRepository,
)
from core.outbox import stage_event


def _stage_pricing_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(orm.PricingOutboxEvent, event_type, payload)


def _admin_ctx(request) -> PricingServiceContext:
    return PricingServiceContext(stage_events=_stage_pricing_events, actor_id=getattr(request.user, "id", None))


# Real, product-required simplification: removed from the Dashboard's
# admin app-index per this phase's own explicit instruction to drop
# the raw "Price List" container CRUD screen -- a second, more
# technical pricing surface next to the friendlier Price List
# dashboard page below, confusing for day-to-day use. Per-variant
# Base/Old/Price editing (the actual daily task) already lives in two
# real, product-name-aware places, unaffected by this removal:
#   1. Product Edit's own "Pricing" section (see
#      `apps.products.infrastructure.admin.ProductPricingInline`).
#   2. The dedicated Price List dashboard page (see
#      `apps.products.infrastructure.price_list_view`), reachable
#      from the main Dashboard's own Quick Actions -- now with a real
#      Stock column too.
# Known, accepted tradeoff: creating a SECOND PriceList container (a
# different currency/region from the default) is no longer reachable
# from the UI -- `_get_or_create_default_price_list()` still transparently
# creates and uses the one default list every real write already goes
# through, so the common single-price-list case is fully unaffected.
# The domain/application layer (PriceListModel, ArchivePriceList, etc.)
# is untouched -- only the admin registration is removed, matching this
# file's own established convention for PriceHistoryEntryAdmin below.
# @admin.register(orm.PriceListModel)
class PriceListAdmin(admin.ModelAdmin):
    """See the removal note above this class for why it's no longer registered."""

    list_display = ("code", "name", "status_badge", "currency", "region", "entry_count")
    list_filter = ("status", "currency", "region")
    search_fields = ("code", "name")
    list_per_page = 25  # Phase 08.7: applying this project's own established default-pagination convention consistently
    readonly_fields = ("id", "created_at", "updated_at", "created_by", "updated_by", "version")
    actions = ["archive_selected"]

    def get_queryset(self, request):
        """Phase 08.7: closes a genuine N+1 -- entry_count() had no prefetch at all, issuing one query per row."""
        return super().get_queryset(request).prefetch_related("entries")

    def status_badge(self, obj: orm.PriceListModel) -> str:
        tones = {"draft": "neutral", "active": "success", "archived": "danger"}
        return format_html('<span class="nz-badge nz-badge-{}">{}</span>', tones.get(obj.status, "neutral"), obj.status)

    status_badge.short_description = "Status"

    def entry_count(self, obj: orm.PriceListModel) -> int:
        """Uses len() on the already-prefetched .all(), not .count() -- per this project's own documented gotcha."""
        return len(obj.entries.all())

    @admin.action(description="Archive selected price lists")
    def archive_selected(self, request, queryset):
        service = ArchivePriceList(DjangoPriceListRepository(), _admin_ctx(request))
        for item in queryset:
            try:
                service.execute(item.id)
            except Exception as exc:  # noqa: BLE001
                self.message_user(request, f"Could not archive {item.code}: {exc}", level="error")


# Real, product-required simplification: removed from Dashboard -- read-only, system-internal (audit/event-log) data an admin never creates or edits by hand.
# @admin.register(orm.PriceHistoryEntryModel)
class PriceHistoryEntryAdmin(admin.ModelAdmin):
    """Read-only -- append-only, per MIC §9."""
    list_per_page = 25  # Phase 08.7: applying this project's own established default-pagination convention consistently

    list_display = ("price_list", "product_variant_id", "price_type", "old_amount", "new_amount", "reason", "changed_at")
    list_filter = ("price_type", "reason")
    readonly_fields = [f.name for f in orm.PriceHistoryEntryModel._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class QuantityTierInline(admin.TabularInline):
    model = orm.QuantityTierModel
    extra = 0


# Real, product-required simplification: removed from the Dashboard's
# admin app-index per this phase's own explicit instruction to drop
# "Price Rules" from the visible admin surface -- a second, more
# technical pricing concept (region/membership-tier/quantity-tier rule
# matching) alongside the one real, day-to-day pricing task (Base/Old/
# Price per variant), which stays fully available via the Price List
# dashboard page and Product Edit's own Pricing section, unaffected by
# this removal. The domain/application layer (PricingRuleModel, etc.)
# is untouched -- only the admin registration is removed, matching
# this file's own established convention for PriceListAdmin above.
# @admin.register(orm.PricingRuleModel)
class PricingRuleAdmin(admin.ModelAdmin):
    list_per_page = 25  # Phase 08.7: applying this project's own established default-pagination convention consistently
    list_display = ("id", "rule_type", "status_badge", "priority", "region", "membership_tier_code")
    list_filter = ("status", "rule_type")
    inlines = [QuantityTierInline]
    readonly_fields = ("id", "created_at", "updated_at")

    def status_badge(self, obj: orm.PricingRuleModel) -> str:
        tones = {"draft": "neutral", "scheduled": "warning", "active": "success", "expired": "danger", "archived": "danger"}
        return format_html('<span class="nz-badge nz-badge-{}">{}</span>', tones.get(obj.status, "neutral"), obj.status)

    status_badge.short_description = "Status"


class CampaignTargetInline(admin.TabularInline):
    model = orm.CampaignTargetModel
    extra = 0


# Real, product-required simplification: removed from the Dashboard --
# this phase's own explicit instruction to drop Campaigns from the
# visible admin surface to avoid unnecessary complexity ("ortiqcha
# murakkablikdan qochamiz"). The domain/application layer (CampaignModel,
# EndCampaign, etc.) is untouched -- only the admin registration is
# removed, matching this file's own established convention for
# PriceHistoryEntryAdmin/PriceSnapshotAdmin/PricingOutboxEvent above.
# @admin.register(orm.CampaignModel)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "campaign_type", "status_badge", "campaign_preview", "validity_starts_at", "validity_ends_at")
    list_filter = ("status", "campaign_type")
    search_fields = ("name",)
    list_per_page = 25  # Phase 08.7: applying this project's own established default-pagination convention consistently
    inlines = [CampaignTargetInline]
    readonly_fields = ("id", "created_at", "updated_at")
    actions = ["end_selected"]

    def get_queryset(self, request):
        """Phase 08.7: closes a genuine N+1 -- campaign_preview() called obj.targets.count() with no prefetch at all, one query per row."""
        return super().get_queryset(request).prefetch_related("targets")

    def status_badge(self, obj: orm.CampaignModel) -> str:
        tones = {"draft": "neutral", "scheduled": "warning", "active": "success", "ended": "danger", "cancelled": "danger"}
        return format_html('<span class="nz-badge nz-badge-{}">{}</span>', tones.get(obj.status, "neutral"), obj.status)

    status_badge.short_description = "Status"

    def campaign_preview(self, obj: orm.CampaignModel) -> str:
        target_count = len(obj.targets.all())  # uses the already-prefetched cache, not .count()
        if obj.discount_value_type == "percentage":
            return f"{obj.discount_percentage}% off, {target_count} target(s)"
        return f"{obj.discount_fixed_amount} {obj.currency} off, {target_count} target(s)"

    campaign_preview.short_description = "Discount"

    @admin.action(description="End selected campaigns")
    def end_selected(self, request, queryset):
        """Phase 08.7: fixed a genuine defect -- the previous `except Exception: pass` silently swallowed every failure with zero user feedback, violating this project's own established error-handling convention (every other bulk action in this file calls self.message_user on failure)."""
        service = EndCampaign(DjangoCampaignRepository(), _admin_ctx(request))
        for item in queryset:
            try:
                service.execute(item.id)
            except Exception as exc:  # noqa: BLE001
                self.message_user(request, f"Could not end campaign '{item.name}': {exc}", level="error")


# Real, product-required simplification: removed from Dashboard -- read-only, system-internal (audit/event-log) data an admin never creates or edits by hand.
# @admin.register(orm.PriceSnapshotModel)
class PriceSnapshotAdmin(admin.ModelAdmin):
    list_per_page = 25  # Phase 08.7: applying this project's own established default-pagination convention consistently
    list_display = ("token", "product_variant_id", "locked_price_amount", "status", "expires_at")
    list_filter = ("status",)
    readonly_fields = ("id", "token", "created_at", "updated_at")


# Real, product-required simplification: removed from Dashboard -- read-only, system-internal (audit/event-log) data an admin never creates or edits by hand.
# @admin.register(orm.PricingOutboxEvent)
class PricingOutboxEventAdmin(admin.ModelAdmin):
    """Read-only -- append-only/Outbox tables are never editable in admin, per MIC §9."""
    list_per_page = 25  # Phase 08.7: applying this project's own established default-pagination convention consistently

    list_display = ("event_type", "event_version", "created_at", "published_at", "publish_attempts")
    list_filter = ("event_type",)
    readonly_fields = [f.name for f in orm.PricingOutboxEvent._meta.fields]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


from apps.pricing.infrastructure import coupon_admin  # noqa: E402,F401  (premium coupons workspace)
