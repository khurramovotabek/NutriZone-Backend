"""
Query Application Services: CalculatePrice, GetPriceHistory,
GetPriceList, ListPriceLists, SearchPricing.

`CalculatePrice` is the single entry point every price-preview/lookup
caller uses -- it assembles `DiscountSource` candidates from whatever
active PricingRules/Campaigns/Coupon match, plus any caller-supplied
Loyalty/Wallet parameters, and hands them to
`PriceCalculationEngine.calculate()` (domain/services.py) exactly
once, per this phase's 'no duplicated pricing calculation' rule.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.utils import timezone as django_timezone

from apps.pricing.application.ports import CampaignRepository, CouponRepository, PriceListRepository, PricingRuleRepository
from apps.pricing.domain.enums import DiscountSourceType, StackingMode
from apps.pricing.domain.services import DiscountSource, PriceCalculationEngine, PriceCalculationResult
from apps.pricing.domain.value_objects import Money
from common.exceptions import ResourceNotFound


class CalculatePrice:
    def __init__(self, price_list_repo: PriceListRepository, rule_repo: PricingRuleRepository, campaign_repo: CampaignRepository, coupon_repo: CouponRepository) -> None:
        self._price_list_repo = price_list_repo
        self._rule_repo = rule_repo
        self._campaign_repo = campaign_repo
        self._coupon_repo = coupon_repo

    def execute(self, price_list_id: uuid.UUID, product_variant_id: uuid.UUID, quantity: int = 1, at: datetime | None = None, coupon_code: str | None = None, region: str | None = None, membership_tier_code: str | None = None) -> PriceCalculationResult:
        at = at or django_timezone.now()
        price_list = self._price_list_repo.get_by_id(price_list_id)
        if price_list is None:
            raise ResourceNotFound("Price list not found.")

        entry = price_list.entry_for_variant(product_variant_id)
        if entry is None:
            raise ResourceNotFound(f"No price is configured for product variant '{product_variant_id}' in this price list.")

        base_price = entry.sale_price or entry.base_price
        sources: list[DiscountSource] = []

        for rule in self._rule_repo.list_active_at(at):
            if rule.rule_type.value == "quantity_discount":
                tier = rule.tier_for_quantity(quantity)
                if tier is not None:
                    sources.append(DiscountSource(source_type=DiscountSourceType.PRICING_RULE.value, source_id=rule.id, label=f"Quantity discount ({tier.minimum_quantity}+)", discount=tier.discount, stacking_mode=StackingMode.STACKABLE.value, priority=rule.priority))
            elif rule.rule_type.value == "regional" and region and rule.region and rule.region.value == region:
                sources.append(DiscountSource(source_type=DiscountSourceType.PRICING_RULE.value, source_id=rule.id, label="Regional pricing", discount=rule.discount, stacking_mode=StackingMode.STACKABLE.value, priority=rule.priority))
            elif rule.rule_type.value == "membership" and membership_tier_code and rule.membership_tier_code == membership_tier_code:
                sources.append(DiscountSource(source_type=DiscountSourceType.MEMBERSHIP.value, source_id=rule.id, label="Membership pricing", discount=rule.discount, stacking_mode=StackingMode.STACKABLE.value, priority=rule.priority))
            elif rule.rule_type.value in ("time_based", "dynamic") and rule.is_active_at(at):
                sources.append(DiscountSource(source_type=DiscountSourceType.PRICING_RULE.value, source_id=rule.id, label="Scheduled pricing", discount=rule.discount, stacking_mode=StackingMode.STACKABLE.value, priority=rule.priority))

        for campaign in self._campaign_repo.list_active_for_target("variant", product_variant_id, at):
            sources.append(DiscountSource(source_type=DiscountSourceType.CAMPAIGN.value, source_id=campaign.id, label=campaign.name, discount=campaign.discount, stacking_mode=campaign.stacking_mode.value, priority=10))

        if coupon_code:
            coupon = self._coupon_repo.get_by_code(coupon_code)
            if coupon is not None:
                coupon.assert_redeemable(at)
                sources.append(DiscountSource(source_type=DiscountSourceType.COUPON.value, source_id=coupon.id, label=f"Coupon {coupon_code}", discount=coupon.discount, stacking_mode=coupon.stacking_mode.value, priority=5))

        return PriceCalculationEngine.calculate(base_price, sources)


class GetPriceHistory:
    def __init__(self, repo: PriceListRepository) -> None:
        self._repo = repo

    def execute(self, price_list_id: uuid.UUID, product_variant_id: uuid.UUID) -> list:
        price_list = self._repo.get_by_id(price_list_id)
        if price_list is None:
            raise ResourceNotFound("Price list not found.")
        return [h for h in price_list.history if h.product_variant_id == product_variant_id]


class GetPriceList:
    def __init__(self, repo: PriceListRepository) -> None:
        self._repo = repo

    def execute(self, code: str):
        price_list = self._repo.get_by_code(code)
        if price_list is None:
            raise ResourceNotFound("Price list not found.")
        return price_list


class ListPriceLists:
    def __init__(self, repo: PriceListRepository) -> None:
        self._repo = repo

    def execute(self, status: str | None = None, page: int = 1, page_size: int = 20):
        return self._repo.list_for_admin(status=status, page=page, page_size=page_size)


class SearchPricing:
    def __init__(self, search_gateway) -> None:
        self._search_gateway = search_gateway

    def execute(self, query: str, filters: dict, page: int = 1, page_size: int = 20):
        return self._search_gateway.search(query=query, filters=filters, page=page, page_size=page_size)
