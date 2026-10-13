"""
Composition root for the `pricing` module's interfaces layer.

Wires concrete `infrastructure/` implementations into `application/
services/` constructors -- matching every prior module's composition
root exactly. No service locator: every `build_*()` factory explicitly
constructs and returns one fully-wired object.
"""
from __future__ import annotations

import uuid

from apps.pricing.application.selectors import PricingSelector as ApplicationPricingSelector
from apps.pricing.application.services._shared import PricingServiceContext
from apps.pricing.application.services.coupons_bundles_snapshots import (
    ConsumePriceSnapshot, CreateCoupon, IssueVariantPriceSnapshot, LockPrice, RedeemCoupon,
    ReleasePriceSnapshot, RevokeCoupon,
)
from apps.pricing.application.services.price_lists import ActivatePriceList, ArchivePriceList, CreatePriceList, SetPrice
from apps.pricing.application.services.queries import CalculatePrice, GetPriceHistory, GetPriceList, ListPriceLists, SearchPricing
from apps.pricing.application.services.rules_and_campaigns import (
    ActivateCampaign, ActivatePricingRule, ArchivePricingRule, CancelCampaign, CreateCampaign, CreatePricingRule, EndCampaign,
)
from apps.pricing.infrastructure import models as orm
from apps.pricing.infrastructure.repositories import (
    DjangoCampaignRepository, DjangoCouponRepository, DjangoPriceListRepository,
    DjangoPriceSnapshotRepository, DjangoPricingRuleRepository,
)
from apps.pricing.infrastructure.selectors import DjangoPricingSearchBackend
from core.outbox import stage_event


def stage_pricing_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(orm.PricingOutboxEvent, event_type, payload)


def build_pricing_service_context(actor_id: uuid.UUID | None = None) -> PricingServiceContext:
    return PricingServiceContext(stage_events=stage_pricing_events, actor_id=actor_id)


# --- Repositories (also directly exposed so no future Interfaces-layer
# view has any reason to instantiate one directly -- the fix already
# applied pre-emptively in every module's infra phase since Store). ---

def build_price_list_repository() -> DjangoPriceListRepository:
    return DjangoPriceListRepository()


def build_pricing_rule_repository() -> DjangoPricingRuleRepository:
    return DjangoPricingRuleRepository()


def build_campaign_repository() -> DjangoCampaignRepository:
    return DjangoCampaignRepository()


def build_coupon_repository() -> DjangoCouponRepository:
    return DjangoCouponRepository()


def build_price_snapshot_repository() -> DjangoPriceSnapshotRepository:
    return DjangoPriceSnapshotRepository()


def build_pricing_selector() -> ApplicationPricingSelector:
    return ApplicationPricingSelector(DjangoPricingSearchBackend())


# --- Price Lists -----------------------------------------------------

def build_create_price_list(actor_id=None) -> CreatePriceList:
    return CreatePriceList(DjangoPriceListRepository(), build_pricing_service_context(actor_id))


def build_activate_price_list(actor_id=None) -> ActivatePriceList:
    return ActivatePriceList(DjangoPriceListRepository(), build_pricing_service_context(actor_id))


def build_archive_price_list(actor_id=None) -> ArchivePriceList:
    return ArchivePriceList(DjangoPriceListRepository(), build_pricing_service_context(actor_id))


def build_set_price(actor_id=None) -> SetPrice:
    return SetPrice(DjangoPriceListRepository(), build_pricing_service_context(actor_id))


# --- Rules & Campaigns -------------------------------------------------

def build_create_pricing_rule(actor_id=None) -> CreatePricingRule:
    return CreatePricingRule(DjangoPricingRuleRepository(), build_pricing_service_context(actor_id))


def build_activate_pricing_rule(actor_id=None) -> ActivatePricingRule:
    return ActivatePricingRule(DjangoPricingRuleRepository(), build_pricing_service_context(actor_id))


def build_archive_pricing_rule(actor_id=None) -> ArchivePricingRule:
    return ArchivePricingRule(DjangoPricingRuleRepository(), build_pricing_service_context(actor_id))


def build_create_campaign(actor_id=None) -> CreateCampaign:
    return CreateCampaign(DjangoCampaignRepository(), build_pricing_service_context(actor_id))


def build_activate_campaign(actor_id=None) -> ActivateCampaign:
    return ActivateCampaign(DjangoCampaignRepository(), build_pricing_service_context(actor_id))


def build_end_campaign(actor_id=None) -> EndCampaign:
    return EndCampaign(DjangoCampaignRepository(), build_pricing_service_context(actor_id))


def build_cancel_campaign(actor_id=None) -> CancelCampaign:
    return CancelCampaign(DjangoCampaignRepository(), build_pricing_service_context(actor_id))


# --- Coupons / Snapshots ----------------------------------------------

def build_create_coupon(actor_id=None) -> CreateCoupon:
    return CreateCoupon(DjangoCouponRepository(), build_pricing_service_context(actor_id))


def build_redeem_coupon(actor_id=None) -> RedeemCoupon:
    return RedeemCoupon(DjangoCouponRepository(), build_pricing_service_context(actor_id))


def build_revoke_coupon(actor_id=None) -> RevokeCoupon:
    return RevokeCoupon(DjangoCouponRepository(), build_pricing_service_context(actor_id))


def build_lock_price(actor_id=None) -> LockPrice:
    return LockPrice(DjangoPriceSnapshotRepository(), build_pricing_service_context(actor_id))


def build_issue_variant_price_snapshot(actor_id=None) -> IssueVariantPriceSnapshot:
    return IssueVariantPriceSnapshot(DjangoPriceListRepository(), build_calculate_price(), build_lock_price(actor_id))


def build_consume_price_snapshot(actor_id=None) -> ConsumePriceSnapshot:
    return ConsumePriceSnapshot(DjangoPriceSnapshotRepository(), build_pricing_service_context(actor_id))


def build_release_price_snapshot(actor_id=None) -> ReleasePriceSnapshot:
    return ReleasePriceSnapshot(DjangoPriceSnapshotRepository(), build_pricing_service_context(actor_id))


# --- Queries --------------------------------------------------------------

def build_calculate_price() -> CalculatePrice:
    return CalculatePrice(DjangoPriceListRepository(), DjangoPricingRuleRepository(), DjangoCampaignRepository(), DjangoCouponRepository())


def build_get_price_history() -> GetPriceHistory:
    return GetPriceHistory(DjangoPriceListRepository())


def build_get_price_list() -> GetPriceList:
    return GetPriceList(DjangoPriceListRepository())


def build_list_price_lists() -> ListPriceLists:
    return ListPriceLists(DjangoPriceListRepository())


def build_search_pricing() -> SearchPricing:
    return SearchPricing(DjangoPricingSearchBackend())
