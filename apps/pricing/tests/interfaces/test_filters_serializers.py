from __future__ import annotations

import pytest
from django.http import QueryDict

from apps.pricing.interfaces.api.v1.filters import (
    parse_campaign_filter_params, parse_coupon_filter_params, parse_pagination, parse_price_list_filter_params,
    parse_pricing_rule_filter_params,
)
from apps.pricing.interfaces.api.v1.serializers import (
    CalculatePriceRequestSerializer, CreateCampaignSerializer, CreateCouponSerializer, CreatePriceListSerializer,
    CreatePricingRuleSerializer, SetPriceSerializer,
)
from common.exceptions import ValidationFailed

pytestmark = pytest.mark.unit


def _qd(params: dict) -> QueryDict:
    qd = QueryDict(mutable=True)
    for key, value in params.items():
        qd[key] = value
    return qd


class TestPriceListFilterParams:
    def test_defaults(self):
        params = parse_price_list_filter_params(_qd({}))
        assert params.page == 1
        assert params.sort == "-created_at"

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationFailed):
            parse_price_list_filter_params(_qd({"filter[status]": "bogus"}))

    def test_invalid_sort_raises(self):
        with pytest.raises(ValidationFailed):
            parse_price_list_filter_params(_qd({"sort": "bogus"}))


class TestPricingRuleFilterParams:
    def test_invalid_status_raises(self):
        with pytest.raises(ValidationFailed):
            parse_pricing_rule_filter_params(_qd({"filter[status]": "bogus"}))

    def test_valid_membership_tier_passthrough(self):
        params = parse_pricing_rule_filter_params(_qd({"filter[membership_tier]": "gold"}))
        assert params.membership_tier_code == "gold"


class TestCampaignFilterParams:
    def test_active_only_flag_parsing(self):
        params = parse_campaign_filter_params(_qd({"filter[active]": "true"}))
        assert params.active_only is True

    def test_active_only_defaults_false(self):
        params = parse_campaign_filter_params(_qd({}))
        assert params.active_only is False


class TestCouponFilterParams:
    def test_invalid_status_raises(self):
        with pytest.raises(ValidationFailed):
            parse_coupon_filter_params(_qd({"filter[status]": "bogus"}))


class TestPagination:
    def test_caps_page_size(self):
        params = parse_pagination(_qd({"page_size": "9999"}))
        assert params.page_size == 100


class TestSerializers:
    def test_create_price_list_serializer_valid(self):
        serializer = CreatePriceListSerializer(data={"code": "DEFAULT-UZS", "name": "Default", "currency": "UZS"})
        assert serializer.is_valid()

    def test_create_price_list_serializer_rejects_invalid_code(self):
        serializer = CreatePriceListSerializer(data={"code": "default!", "name": "Default", "currency": "UZS"})
        assert not serializer.is_valid()
        assert "code" in serializer.errors

    def test_set_price_serializer_rejects_negative_base_amount(self):
        import uuid

        serializer = SetPriceSerializer(data={"product_variant_id": str(uuid.uuid4()), "base_amount": "-10.00", "currency": "UZS"})
        assert not serializer.is_valid()

    def test_create_pricing_rule_serializer_requires_valid_rule_type(self):
        serializer = CreatePricingRuleSerializer(data={"rule_type": "bogus_type", "discount_value_type": "percentage", "discount_percentage": "10"})
        assert not serializer.is_valid()

    def test_create_campaign_serializer_requires_starts_at(self):
        serializer = CreateCampaignSerializer(data={"campaign_type": "flash_sale", "name": "Sale", "discount_value_type": "percentage", "discount_percentage": "20"})
        assert not serializer.is_valid()
        assert "starts_at" in serializer.errors

    def test_create_coupon_serializer_validates_code_format(self):
        serializer = CreateCouponSerializer(data={"code": "bad code!", "coupon_type": "coupon", "discount_value_type": "percentage", "discount_percentage": "10"})
        assert not serializer.is_valid()

    def test_calculate_price_request_serializer_defaults_quantity_to_one(self):
        import uuid

        serializer = CalculatePriceRequestSerializer(data={"price_list_id": str(uuid.uuid4()), "product_variant_id": str(uuid.uuid4())})
        assert serializer.is_valid()
        assert serializer.validated_data["quantity"] == 1

    def test_calculate_price_request_serializer_rejects_zero_quantity(self):
        import uuid

        serializer = CalculatePriceRequestSerializer(data={"price_list_id": str(uuid.uuid4()), "product_variant_id": str(uuid.uuid4()), "quantity": 0})
        assert not serializer.is_valid()
