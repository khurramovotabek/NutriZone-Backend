"""
PricingRule & Campaign Application Services: CreatePricingRule,
ActivatePricingRule, ArchivePricingRule, CreateCampaign,
ActivateCampaign, EndCampaign, CancelCampaign.
"""
from __future__ import annotations

import uuid

from django.db import transaction

from apps.pricing.application.ports import CampaignRepository, PricingRuleRepository
from apps.pricing.application.services._shared import PricingServiceContext
from apps.pricing.domain.aggregates import Campaign, PricingRule
from apps.pricing.domain.entities import CampaignTarget
from apps.pricing.domain.enums import CampaignType, PricingRuleType, StackingMode
from apps.pricing.domain.value_objects import DiscountValue, Percentage, PriceValidityPeriod, RegionCode
from common.exceptions import ResourceNotFound


def _discount_from_params(value_type: str, percentage=None, fixed_amount=None, currency: str = "UZS") -> DiscountValue:
    from apps.pricing.domain.value_objects import Money

    return DiscountValue(
        value_type=value_type,
        percentage=Percentage(value=percentage) if percentage is not None else None,
        fixed_amount=Money(amount=fixed_amount, currency=currency) if fixed_amount is not None else None,
    )


class CreatePricingRule:
    def __init__(self, repo: PricingRuleRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, rule_type: str, discount_value_type: str, discount_percentage=None, discount_fixed_amount=None, currency: str = "UZS", region: str | None = None, membership_tier_code: str | None = None, priority: int = 100) -> PricingRule:
        rule = PricingRule(
            id=uuid.uuid4(), rule_type=PricingRuleType(rule_type), discount=_discount_from_params(discount_value_type, discount_percentage, discount_fixed_amount, currency),
            region=RegionCode(region) if region else None, membership_tier_code=membership_tier_code, priority=priority,
        )
        saved = self._repo.save(rule)

        from apps.pricing.domain.events import PricingRuleCreated

        self._ctx.stage_events([("PricingRuleCreated", PricingRuleCreated(pricing_rule_id=saved.id, rule_type=rule_type).to_payload())])
        self._ctx.audit().created(entity_type="PricingRule", entity_id=str(saved.id), after={"rule_type": rule_type})
        self._ctx.invalidate_pricing_cache()
        self._ctx.metric("pricing_rules_created_total")
        return saved


class ActivatePricingRule:
    def __init__(self, repo: PricingRuleRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, pricing_rule_id: uuid.UUID) -> PricingRule:
        rule = self._repo.get_by_id(pricing_rule_id)
        if rule is None:
            raise ResourceNotFound("Pricing rule not found.")
        event = rule.activate()
        saved = self._repo.save(rule)
        self._ctx.stage_events([("PricingRuleActivated", event.to_payload())])
        self._ctx.audit().updated(entity_type="PricingRule", entity_id=str(pricing_rule_id), before={}, after={"status": "active"})
        self._ctx.invalidate_pricing_cache()
        return saved


class ArchivePricingRule:
    def __init__(self, repo: PricingRuleRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, pricing_rule_id: uuid.UUID) -> PricingRule:
        rule = self._repo.get_by_id(pricing_rule_id)
        if rule is None:
            raise ResourceNotFound("Pricing rule not found.")
        event = rule.archive()
        saved = self._repo.save(rule)
        self._ctx.stage_events([("PricingRuleArchived", event.to_payload())])
        self._ctx.audit().updated(entity_type="PricingRule", entity_id=str(pricing_rule_id), before={}, after={"status": "archived"})
        self._ctx.invalidate_pricing_cache()
        return saved


class CreateCampaign:
    def __init__(self, repo: CampaignRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, campaign_type: str, name: str, discount_value_type: str, starts_at, ends_at=None, discount_percentage=None, discount_fixed_amount=None, currency: str = "UZS", stacking_mode: str = StackingMode.EXCLUSIVE.value, target_variant_ids: list[uuid.UUID] | None = None) -> Campaign:
        campaign = Campaign(
            id=uuid.uuid4(), campaign_type=CampaignType(campaign_type), name=name,
            discount=_discount_from_params(discount_value_type, discount_percentage, discount_fixed_amount, currency),
            validity=PriceValidityPeriod(starts_at=starts_at, ends_at=ends_at), stacking_mode=StackingMode(stacking_mode),
        )
        for variant_id in target_variant_ids or []:
            campaign.add_target(CampaignTarget(id=uuid.uuid4(), target_type="variant", target_id=variant_id))
        saved = self._repo.save(campaign)

        from apps.pricing.domain.events import CampaignCreated

        self._ctx.stage_events([("CampaignCreated", CampaignCreated(campaign_id=saved.id, campaign_type=campaign_type).to_payload())])
        self._ctx.audit().created(entity_type="Campaign", entity_id=str(saved.id), after={"name": name, "campaign_type": campaign_type})
        self._ctx.invalidate_pricing_cache()
        self._ctx.metric("campaigns_created_total")
        return saved


class ActivateCampaign:
    def __init__(self, repo: CampaignRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = self._repo.get_by_id(campaign_id)
        if campaign is None:
            raise ResourceNotFound("Campaign not found.")
        event = campaign.activate()
        saved = self._repo.save(campaign)
        self._ctx.stage_events([("CampaignActivated", event.to_payload())])
        self._ctx.audit().updated(entity_type="Campaign", entity_id=str(campaign_id), before={}, after={"status": "active"})
        self._ctx.invalidate_pricing_cache()
        self._ctx.metric("campaigns_activated_total")
        return saved


class EndCampaign:
    def __init__(self, repo: CampaignRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = self._repo.get_by_id(campaign_id)
        if campaign is None:
            raise ResourceNotFound("Campaign not found.")
        event = campaign.end()
        saved = self._repo.save(campaign)
        self._ctx.stage_events([("CampaignEnded", event.to_payload())])
        self._ctx.audit().updated(entity_type="Campaign", entity_id=str(campaign_id), before={}, after={"status": "ended"})
        self._ctx.invalidate_pricing_cache()
        return saved


class CancelCampaign:
    def __init__(self, repo: CampaignRepository, ctx: PricingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = self._repo.get_by_id(campaign_id)
        if campaign is None:
            raise ResourceNotFound("Campaign not found.")
        event = campaign.cancel()
        saved = self._repo.save(campaign)
        self._ctx.stage_events([("CampaignCancelled", event.to_payload())])
        self._ctx.audit().updated(entity_type="Campaign", entity_id=str(campaign_id), before={}, after={"status": "cancelled"})
        self._ctx.invalidate_pricing_cache()
        return saved
