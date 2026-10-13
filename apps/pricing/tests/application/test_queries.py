from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone as django_timezone

from apps.pricing.application.services.queries import CalculatePrice, GetPriceHistory, GetPriceList, ListPriceLists, SearchPricing
from apps.pricing.domain.aggregates import Campaign, PriceList, PricingRule
from apps.pricing.domain.enums import CampaignType, PricingRuleType
from apps.pricing.domain.value_objects import DiscountValue, Money, Percentage, PriceListCode, PriceValidityPeriod
from apps.pricing.tests.application.fakes import FakeCampaignRepository, FakeCouponRepository, FakePriceListRepository, FakePricingRuleRepository
from common.exceptions import ResourceNotFound


def _pct(value: str) -> DiscountValue:
    return DiscountValue(value_type="percentage", percentage=Percentage(value=Decimal(value)))


class TestCalculatePrice:
    def test_calculates_from_base_price_with_no_rules(self):
        price_list_repo = FakePriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS")
        variant_id = uuid.uuid4()
        price_list.set_price(variant_id, Money(amount=Decimal("100.00"), currency="UZS"))
        price_list_repo.save(price_list)

        service = CalculatePrice(price_list_repo, FakePricingRuleRepository(), FakeCampaignRepository(), FakeCouponRepository())
        result = service.execute(price_list.id, variant_id)
        assert result.final_price.amount == Decimal("100.00")

    def test_uses_sale_price_over_base_price_when_present(self):
        price_list_repo = FakePriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS")
        variant_id = uuid.uuid4()
        price_list.set_price(variant_id, Money(amount=Decimal("100.00"), currency="UZS"), sale_price=Money(amount=Decimal("80.00"), currency="UZS"))
        price_list_repo.save(price_list)

        service = CalculatePrice(price_list_repo, FakePricingRuleRepository(), FakeCampaignRepository(), FakeCouponRepository())
        result = service.execute(price_list.id, variant_id)
        assert result.base_price.amount == Decimal("80.00")

    def test_missing_price_list_raises(self):
        service = CalculatePrice(FakePriceListRepository(), FakePricingRuleRepository(), FakeCampaignRepository(), FakeCouponRepository())
        with pytest.raises(ResourceNotFound):
            service.execute(uuid.uuid4(), uuid.uuid4())

    def test_missing_variant_entry_raises(self):
        price_list_repo = FakePriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS")
        price_list_repo.save(price_list)

        service = CalculatePrice(price_list_repo, FakePricingRuleRepository(), FakeCampaignRepository(), FakeCouponRepository())
        with pytest.raises(ResourceNotFound):
            service.execute(price_list.id, uuid.uuid4())

    def test_applies_active_campaign_targeting_the_variant(self):
        price_list_repo = FakePriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS")
        variant_id = uuid.uuid4()
        price_list.set_price(variant_id, Money(amount=Decimal("100.00"), currency="UZS"))
        price_list_repo.save(price_list)

        campaign_repo = FakeCampaignRepository()
        from apps.pricing.domain.entities import CampaignTarget

        campaign = Campaign(id=uuid.uuid4(), campaign_type=CampaignType.FLASH_SALE, name="Sale", discount=_pct("25"), validity=PriceValidityPeriod(starts_at=django_timezone.now() - timedelta(hours=1), ends_at=django_timezone.now() + timedelta(hours=1)))
        campaign.add_target(CampaignTarget(id=uuid.uuid4(), target_type="variant", target_id=variant_id))
        campaign.activate()
        campaign_repo.save(campaign)

        service = CalculatePrice(price_list_repo, FakePricingRuleRepository(), campaign_repo, FakeCouponRepository())
        result = service.execute(price_list.id, variant_id)
        assert result.final_price.amount == Decimal("75.00")

    def test_applies_quantity_discount_rule_when_quantity_qualifies(self):
        price_list_repo = FakePriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS")
        variant_id = uuid.uuid4()
        price_list.set_price(variant_id, Money(amount=Decimal("100.00"), currency="UZS"))
        price_list_repo.save(price_list)

        rule_repo = FakePricingRuleRepository()
        from apps.pricing.domain.value_objects import QuantityTier

        rule = PricingRule(id=uuid.uuid4(), rule_type=PricingRuleType.QUANTITY_DISCOUNT, discount=_pct("5"), quantity_tiers=(QuantityTier(minimum_quantity=10, discount=_pct("10")),))
        rule.activate()
        rule_repo.save(rule)

        service = CalculatePrice(price_list_repo, rule_repo, FakeCampaignRepository(), FakeCouponRepository())
        result = service.execute(price_list.id, variant_id, quantity=12)
        assert result.final_price.amount == Decimal("90.00")

    def test_quantity_below_tier_threshold_gets_no_discount(self):
        price_list_repo = FakePriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS")
        variant_id = uuid.uuid4()
        price_list.set_price(variant_id, Money(amount=Decimal("100.00"), currency="UZS"))
        price_list_repo.save(price_list)

        rule_repo = FakePricingRuleRepository()
        from apps.pricing.domain.value_objects import QuantityTier

        rule = PricingRule(id=uuid.uuid4(), rule_type=PricingRuleType.QUANTITY_DISCOUNT, discount=_pct("5"), quantity_tiers=(QuantityTier(minimum_quantity=10, discount=_pct("10")),))
        rule.activate()
        rule_repo.save(rule)

        service = CalculatePrice(price_list_repo, rule_repo, FakeCampaignRepository(), FakeCouponRepository())
        result = service.execute(price_list.id, variant_id, quantity=3)
        assert result.final_price.amount == Decimal("100.00")


class TestOtherQueries:
    def test_get_price_history(self):
        repo = FakePriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS")
        variant_id = uuid.uuid4()
        price_list.set_price(variant_id, Money(amount=Decimal("100.00"), currency="UZS"))
        repo.save(price_list)

        history = GetPriceHistory(repo).execute(price_list.id, variant_id)
        assert len(history) == 1

    def test_get_price_history_missing_list_raises(self):
        with pytest.raises(ResourceNotFound):
            GetPriceHistory(FakePriceListRepository()).execute(uuid.uuid4(), uuid.uuid4())

    def test_get_price_list_by_code(self):
        repo = FakePriceListRepository()
        price_list = PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS")
        repo.save(price_list)
        found = GetPriceList(repo).execute("DEFAULT-UZS")
        assert found.id == price_list.id

    def test_list_price_lists(self):
        repo = FakePriceListRepository()
        repo.save(PriceList(id=uuid.uuid4(), code=PriceListCode("DEFAULT-UZS"), name="Default", currency="UZS"))
        results, total = ListPriceLists(repo).execute()
        assert total == 1

    def test_search_pricing(self):
        class _FakeSearchGateway:
            def search(self, query, filters, page, page_size):
                return [{"code": "DEFAULT-UZS"}], 1

        results, total = SearchPricing(_FakeSearchGateway()).execute("default", {})
        assert total == 1
