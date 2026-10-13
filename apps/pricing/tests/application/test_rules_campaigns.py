from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from apps.pricing.application.services._shared import PricingServiceContext
from apps.pricing.application.services.rules_and_campaigns import (
    ActivateCampaign, ActivatePricingRule, ArchivePricingRule, CancelCampaign, CreateCampaign, CreatePricingRule, EndCampaign,
)
from apps.pricing.tests.application.fakes import FakeCampaignRepository, FakePricingRuleRepository, collect_events
from common.exceptions import ResourceNotFound

pytestmark = pytest.mark.django_db


def _ctx():
    events: list = []
    return PricingServiceContext(stage_events=collect_events(events), actor_id=uuid.uuid4()), events


class TestCreateAndLifecyclePricingRule:
    def test_creates_dynamic_rule(self):
        repo = FakePricingRuleRepository()
        ctx, events = _ctx()
        rule = CreatePricingRule(repo, ctx).execute(rule_type="dynamic", discount_value_type="percentage", discount_percentage=Decimal("10"))
        assert rule.status.value == "draft"
        assert any(e[0] == "PricingRuleCreated" for e in events)

    def test_creates_regional_rule(self):
        repo = FakePricingRuleRepository()
        ctx, _ = _ctx()
        rule = CreatePricingRule(repo, ctx).execute(rule_type="regional", discount_value_type="percentage", discount_percentage=Decimal("5"), region="UZ-TASH")
        assert rule.region.value == "UZ-TASH"

    def test_creates_membership_rule(self):
        repo = FakePricingRuleRepository()
        ctx, _ = _ctx()
        rule = CreatePricingRule(repo, ctx).execute(rule_type="membership", discount_value_type="percentage", discount_percentage=Decimal("15"), membership_tier_code="gold")
        assert rule.membership_tier_code == "gold"

    def test_activate_then_archive(self):
        repo = FakePricingRuleRepository()
        ctx, events = _ctx()
        rule = CreatePricingRule(repo, ctx).execute(rule_type="dynamic", discount_value_type="percentage", discount_percentage=Decimal("10"))

        activated = ActivatePricingRule(repo, ctx).execute(rule.id)
        assert activated.status.value == "active"

        archived = ArchivePricingRule(repo, ctx).execute(rule.id)
        assert archived.status.value == "archived"
        event_types = [e[0] for e in events]
        assert "PricingRuleActivated" in event_types
        assert "PricingRuleArchived" in event_types

    def test_activate_missing_rule_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            ActivatePricingRule(FakePricingRuleRepository(), ctx).execute(uuid.uuid4())


class TestCreateAndLifecycleCampaign:
    def test_creates_flash_sale_with_targets(self):
        repo = FakeCampaignRepository()
        ctx, events = _ctx()
        variant_id = uuid.uuid4()
        now = datetime.utcnow()

        campaign = CreateCampaign(repo, ctx).execute(
            campaign_type="flash_sale", name="Weekend Flash Sale", discount_value_type="percentage", discount_percentage=Decimal("30"),
            starts_at=now, ends_at=now + timedelta(days=2), target_variant_ids=[variant_id],
        )
        assert len(campaign.targets) == 1
        assert any(e[0] == "CampaignCreated" for e in events)

    def test_full_lifecycle_activate_end(self):
        repo = FakeCampaignRepository()
        ctx, events = _ctx()
        now = datetime.utcnow()
        campaign = CreateCampaign(repo, ctx).execute(campaign_type="campaign", name="Spring Sale", discount_value_type="fixed_amount", discount_fixed_amount=Decimal("10.00"), starts_at=now)

        activated = ActivateCampaign(repo, ctx).execute(campaign.id)
        assert activated.status.value == "active"

        ended = EndCampaign(repo, ctx).execute(campaign.id)
        assert ended.status.value == "ended"
        event_types = [e[0] for e in events]
        assert "CampaignActivated" in event_types
        assert "CampaignEnded" in event_types

    def test_cancel_campaign(self):
        repo = FakeCampaignRepository()
        ctx, events = _ctx()
        now = datetime.utcnow()
        campaign = CreateCampaign(repo, ctx).execute(campaign_type="campaign", name="Cancelled Sale", discount_value_type="percentage", discount_percentage=Decimal("10"), starts_at=now)

        cancelled = CancelCampaign(repo, ctx).execute(campaign.id)
        assert cancelled.status.value == "cancelled"
        assert any(e[0] == "CampaignCancelled" for e in events)

    def test_end_missing_campaign_raises(self):
        ctx, _ = _ctx()
        with pytest.raises(ResourceNotFound):
            EndCampaign(FakeCampaignRepository(), ctx).execute(uuid.uuid4())
