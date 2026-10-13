"""
Pricing API views.

Thin per Django Implementation Blueprint §3: each view deserializes,
calls exactly one Application Service or Selector (built/accessed via
infrastructure/composition.py), and returns through the standard
response envelope. Every collection endpoint (list+create) is ONE
view class on ONE path -- avoiding the routing bug class already found
and fixed in Products, by construction here. No view instantiates a
repository, imports infrastructure.models, constructs a domain
aggregate, or performs a pricing calculation itself -- CalculatePrice
is the sole entry point for any price computation.
"""
from __future__ import annotations

import uuid

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.pricing.infrastructure import composition
from apps.pricing.interfaces.api.v1.filters import (
    parse_campaign_filter_params, parse_coupon_filter_params, parse_pagination, parse_price_list_filter_params,
    parse_pricing_rule_filter_params,
)
from apps.pricing.interfaces.api.v1.permissions import (
    CanCalculatePrices, CanIssuePriceSnapshot, CanManageCampaigns, CanManageCoupons, CanManagePriceLists,
    CanManagePricingRules, CanManageSnapshots, CanPreviewPrices, CanViewPricing, CanViewPriceHistory,
)
from apps.pricing.interfaces.api.v1.serializers import (
    CalculatePriceRequestSerializer, CreateCampaignSerializer, CreateCouponSerializer,
    CreatePriceListSerializer, CreatePricingRuleSerializer, IssueVariantPriceSnapshotSerializer, LockPriceSerializer, RedeemCouponSerializer, SetPriceSerializer,
)
from common.exceptions import ResourceNotFound
from common.idempotency import protect_with_idempotency
from common.responses import paginated_response, success_response
from core.openapi import STANDARD_ERROR_RESPONSES
from core.ratelimit import ScopedRateLimitThrottle


def _responses(*codes: int) -> dict:
    return {code: STANDARD_ERROR_RESPONSES[code] for code in codes}


def _attach_identity(request) -> None:
    request.identity = request.user


def _actor_id(request):
    return getattr(getattr(request, "user", None), "id", None)


class PricingAdminThrottle(ScopedRateLimitThrottle):
    scope = "pricing.admin_operation"
    limit = 600
    window_seconds = 3600
    identifier_source = "user"


class PriceCalculationThrottle(ScopedRateLimitThrottle):
    scope = "pricing.calculation"
    limit = 2000
    window_seconds = 3600
    identifier_source = "user"


def _price_list_payload(price_list) -> dict:
    return {"id": str(price_list.id), "code": price_list.code.value, "name": price_list.name, "currency": price_list.currency, "status": price_list.status.value, "region": price_list.region.value if price_list.region else None}


def _pricing_rule_payload(rule) -> dict:
    return {"id": str(rule.id), "rule_type": rule.rule_type.value, "status": rule.status.value, "priority": rule.priority, "region": rule.region.value if rule.region else None, "membership_tier_code": rule.membership_tier_code}


def _campaign_payload(campaign) -> dict:
    return {"id": str(campaign.id), "campaign_type": campaign.campaign_type.value, "name": campaign.name, "status": campaign.status.value, "stacking_mode": campaign.stacking_mode.value, "target_count": len(campaign.targets)}


def _coupon_payload(coupon) -> dict:
    return {"id": str(coupon.id), "code": coupon.code.value, "coupon_type": coupon.coupon_type.value, "status": coupon.status.value, "redemption_count": coupon.redemption_count, "max_redemptions": coupon.max_redemptions}


def _price_snapshot_payload(snapshot) -> dict:
    return {"id": str(snapshot.id), "token": str(snapshot.token), "product_variant_id": str(snapshot.product_variant_id), "locked_price_amount": str(snapshot.locked_price.amount), "expires_at": snapshot.expires_at.isoformat(), "status": snapshot.status.value}


def _calculation_result_payload(result) -> dict:
    from apps.pricing.domain.services import PricePreviewPolicy

    return PricePreviewPolicy.summarize(result)


# ============================================================
# Price Lists
# ============================================================


class PriceListListCreateView(APIView):
    """Combined GET (list) + POST (create) at one path."""

    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManagePriceLists()] if self.request.method == "POST" else [CanViewPricing()]

    @extend_schema(tags=["Pricing"], summary="List price lists", responses={200: OpenApiResponse(description="Price list collection"), **_responses(401, 403, 422)})
    def get(self, request):
        _attach_identity(request)
        params = parse_price_list_filter_params(request.query_params)
        items, total = composition.build_list_price_lists().execute(status=params.status, page=params.page, page_size=params.page_size)
        total_pages = max((total + params.page_size - 1) // params.page_size, 1)
        return paginated_response(data=[_price_list_payload(p) for p in items], pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Pricing Admin"], summary="Create a price list", request=CreatePriceListSerializer, responses={201: OpenApiResponse(description="Price list created"), **_responses(401, 403, 409, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreatePriceListSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        price_list = composition.build_create_price_list(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_price_list_payload(price_list), status_code=201)


class PriceListDetailView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Pricing"], summary="Get an active price list by code", responses={200: OpenApiResponse(description="Price list detail"), **_responses(404)})
    def get(self, request, code: str):
        price_list = composition.build_get_price_list().execute(code)
        return success_response(data=_price_list_payload(price_list))


class ActivatePriceListView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManagePriceLists()]

    @extend_schema(tags=["Pricing Admin"], summary="Activate a price list", responses={200: OpenApiResponse(description="Activated"), **_responses(401, 403, 404, 409)})
    def post(self, request, price_list_id: str):
        _attach_identity(request)
        price_list = composition.build_activate_price_list(_actor_id(request)).execute(uuid.UUID(price_list_id))
        return success_response(data=_price_list_payload(price_list))


class ArchivePriceListView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManagePriceLists()]

    @extend_schema(tags=["Pricing Admin"], summary="Archive a price list", responses={200: OpenApiResponse(description="Archived"), **_responses(401, 403, 404, 409)})
    def post(self, request, price_list_id: str):
        _attach_identity(request)
        price_list = composition.build_archive_price_list(_actor_id(request)).execute(uuid.UUID(price_list_id))
        return success_response(data=_price_list_payload(price_list))


class SetPriceView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManagePriceLists()]

    @extend_schema(tags=["Pricing Admin"], summary="Set Base/Cost/Sale/Compare-at price for a variant", request=SetPriceSerializer, responses={200: OpenApiResponse(description="Price set"), **_responses(401, 403, 404, 422)})
    def post(self, request, price_list_id: str):
        _attach_identity(request)
        serializer = SetPriceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        price_list = composition.build_set_price(_actor_id(request)).execute(price_list_id=uuid.UUID(price_list_id), **serializer.validated_data)
        return success_response(data=_price_list_payload(price_list))


class PriceHistoryView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanViewPriceHistory()]

    @extend_schema(tags=["Pricing Admin"], summary="Get price history for a variant within a price list", responses={200: OpenApiResponse(description="Price history"), **_responses(401, 403, 404)})
    def get(self, request, price_list_id: str, product_variant_id: str):
        _attach_identity(request)
        history = composition.build_get_price_history().execute(uuid.UUID(price_list_id), uuid.UUID(product_variant_id))
        return success_response(data=[{"id": str(h.id), "price_type": h.price_type, "old_amount": str(h.old_amount.amount) if h.old_amount else None, "new_amount": str(h.new_amount.amount), "reason": h.reason, "changed_at": h.changed_at.isoformat()} for h in history])


# ============================================================
# Pricing Rules
# ============================================================


class PricingRuleListCreateView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManagePricingRules()]

    @extend_schema(tags=["Pricing Admin"], summary="List active pricing rules")
    def get(self, request):
        _attach_identity(request)
        params = parse_pricing_rule_filter_params(request.query_params)
        from apps.pricing.infrastructure.selectors import PricingRuleSelector

        return success_response(data=PricingRuleSelector().list_active(rule_type=params.rule_type))

    @extend_schema(tags=["Pricing Admin"], summary="Create a pricing rule", request=CreatePricingRuleSerializer, responses={201: OpenApiResponse(description="Rule created"), **_responses(401, 403, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreatePricingRuleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rule = composition.build_create_pricing_rule(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_pricing_rule_payload(rule), status_code=201)


class ActivatePricingRuleView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManagePricingRules()]

    @extend_schema(tags=["Pricing Admin"], summary="Activate a pricing rule", responses={200: OpenApiResponse(description="Activated"), **_responses(401, 403, 404, 409)})
    def post(self, request, pricing_rule_id: str):
        _attach_identity(request)
        rule = composition.build_activate_pricing_rule(_actor_id(request)).execute(uuid.UUID(pricing_rule_id))
        return success_response(data=_pricing_rule_payload(rule))


class ArchivePricingRuleView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManagePricingRules()]

    @extend_schema(tags=["Pricing Admin"], summary="Archive a pricing rule", responses={200: OpenApiResponse(description="Archived"), **_responses(401, 403, 404, 409)})
    def post(self, request, pricing_rule_id: str):
        _attach_identity(request)
        rule = composition.build_archive_pricing_rule(_actor_id(request)).execute(uuid.UUID(pricing_rule_id))
        return success_response(data=_pricing_rule_payload(rule))


# ============================================================
# Campaigns
# ============================================================


class CampaignListCreateView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManageCampaigns()]

    @extend_schema(tags=["Pricing Admin"], summary="List active campaigns")
    def get(self, request):
        _attach_identity(request)
        params = parse_campaign_filter_params(request.query_params)
        from apps.pricing.infrastructure.selectors import CampaignSelector

        return success_response(data=CampaignSelector().list_active())

    @extend_schema(tags=["Pricing Admin"], summary="Create a campaign (Flash Sale or Campaign Pricing)", request=CreateCampaignSerializer, responses={201: OpenApiResponse(description="Campaign created"), **_responses(401, 403, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateCampaignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        campaign = composition.build_create_campaign(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_campaign_payload(campaign), status_code=201)


class ActivateCampaignView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManageCampaigns()]

    @extend_schema(tags=["Pricing Admin"], summary="Activate a campaign", responses={200: OpenApiResponse(description="Activated"), **_responses(401, 403, 404, 409)})
    def post(self, request, campaign_id: str):
        _attach_identity(request)
        campaign = composition.build_activate_campaign(_actor_id(request)).execute(uuid.UUID(campaign_id))
        return success_response(data=_campaign_payload(campaign))


class EndCampaignView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManageCampaigns()]

    @extend_schema(tags=["Pricing Admin"], summary="End a campaign", responses={200: OpenApiResponse(description="Ended"), **_responses(401, 403, 404, 409)})
    def post(self, request, campaign_id: str):
        _attach_identity(request)
        campaign = composition.build_end_campaign(_actor_id(request)).execute(uuid.UUID(campaign_id))
        return success_response(data=_campaign_payload(campaign))


class CancelCampaignView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManageCampaigns()]

    @extend_schema(tags=["Pricing Admin"], summary="Cancel a campaign", responses={200: OpenApiResponse(description="Cancelled"), **_responses(401, 403, 404, 409)})
    def post(self, request, campaign_id: str):
        _attach_identity(request)
        campaign = composition.build_cancel_campaign(_actor_id(request)).execute(uuid.UUID(campaign_id))
        return success_response(data=_campaign_payload(campaign))


# ============================================================
# Coupons
# ============================================================


class CouponListCreateView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManageCoupons()]

    @extend_schema(tags=["Pricing Admin"], summary="List active coupons")
    def get(self, request):
        _attach_identity(request)
        from apps.pricing.infrastructure.selectors import CouponSelector

        return success_response(data=CouponSelector().list_active())

    @extend_schema(tags=["Pricing Admin"], summary="Create a coupon", request=CreateCouponSerializer, responses={201: OpenApiResponse(description="Coupon created"), **_responses(401, 403, 409, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        coupon = composition.build_create_coupon(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_coupon_payload(coupon), status_code=201)


class RedeemCouponView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManageCoupons()]

    @extend_schema(tags=["Pricing Admin"], summary="Redeem a coupon by code", request=RedeemCouponSerializer, responses={200: OpenApiResponse(description="Redeemed"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request, code: str):
        _attach_identity(request)
        serializer = RedeemCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return protect_with_idempotency(
            request, _actor_id(request), "pricing.redeem_coupon", {"code": code, **serializer.validated_data},
            operation=lambda: composition.build_redeem_coupon(_actor_id(request)).execute(code=code, **serializer.validated_data),
            result_to_payload=_coupon_payload,
        )


class RevokeCouponView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManageCoupons()]

    @extend_schema(tags=["Pricing Admin"], summary="Revoke a coupon", responses={200: OpenApiResponse(description="Revoked"), **_responses(401, 403, 404, 409)})
    def post(self, request, coupon_id: str):
        _attach_identity(request)
        coupon = composition.build_revoke_coupon(_actor_id(request)).execute(uuid.UUID(coupon_id))
        return success_response(data=_coupon_payload(coupon))


# ============================================================
# Snapshots
# ============================================================


class LockPriceView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManageSnapshots()]

    @extend_schema(tags=["Pricing Admin"], summary="Lock (snapshot) a price for a bounded window", request=LockPriceSerializer, responses={201: OpenApiResponse(description="Price locked"), **_responses(401, 403, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = LockPriceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        snapshot = composition.build_lock_price(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_price_snapshot_payload(snapshot), status_code=201)


class ConsumePriceSnapshotView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManageSnapshots()]

    @extend_schema(tags=["Pricing Admin"], summary="Consume a locked price snapshot", responses={200: OpenApiResponse(description="Consumed"), **_responses(401, 403, 404, 409)})
    def post(self, request, snapshot_id: str):
        _attach_identity(request)
        snapshot = composition.build_consume_price_snapshot(_actor_id(request)).execute(uuid.UUID(snapshot_id))
        return success_response(data=_price_snapshot_payload(snapshot))


class ReleasePriceSnapshotView(APIView):
    throttle_classes = [PricingAdminThrottle]

    def get_permissions(self):
        return [CanManageSnapshots()]

    @extend_schema(tags=["Pricing Admin"], summary="Release a locked price snapshot without consuming it", responses={200: OpenApiResponse(description="Released"), **_responses(401, 403, 404, 409)})
    def post(self, request, snapshot_id: str):
        _attach_identity(request)
        snapshot = composition.build_release_price_snapshot(_actor_id(request)).execute(uuid.UUID(snapshot_id))
        return success_response(data=_price_snapshot_payload(snapshot))


# ============================================================
# Price Calculation / Preview / Search
# ============================================================


class CalculatePriceView(APIView):
    throttle_classes = [PriceCalculationThrottle]

    def get_permissions(self):
        return [CanCalculatePrices()]

    @extend_schema(tags=["Pricing"], summary="Calculate the effective price for a variant, applying all matching rules/campaigns/coupon", request=CalculatePriceRequestSerializer, responses={200: OpenApiResponse(description="Calculation result"), **_responses(401, 403, 404, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CalculatePriceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = composition.build_calculate_price().execute(**serializer.validated_data)
        return success_response(data=_calculation_result_payload(result))


class PreviewPriceView(APIView):
    """Same underlying computation as CalculatePriceView -- a distinct, read-only-flavored permission (CanPreviewPrices, typically granted more broadly than CanCalculatePrices) for admin merchandising 'what would this price be' tooling, per this phase's explicit 'Price Preview' capability. Never re-implements the calculation; delegates to the identical CalculatePrice Application Service."""

    throttle_classes = [PriceCalculationThrottle]

    def get_permissions(self):
        return [CanPreviewPrices()]

    @extend_schema(tags=["Pricing"], summary="Preview the effective price for a variant (read-only, same engine as /calculate)", request=CalculatePriceRequestSerializer, responses={200: OpenApiResponse(description="Preview result"), **_responses(401, 403, 404, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CalculatePriceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = composition.build_calculate_price().execute(**serializer.validated_data)
        return success_response(data=_calculation_result_payload(result))


class IssueVariantPriceSnapshotView(APIView):
    """
    Phase 09.4: the new, customer-safe endpoint this project was
    missing. Unlike CalculatePriceView/LockPriceView (both
    admin-permission-gated and requiring a caller-supplied
    price_list_id or locked_amount), this endpoint takes only
    contextual inputs and resolves the active price list and the
    real price entirely server-side via IssueVariantPriceSnapshot,
    which itself composes the existing, certified CalculatePrice and
    LockPrice services -- no new pricing engine, no client-supplied
    monetary value accepted anywhere in this chain.
    """

    throttle_classes = [PriceCalculationThrottle]

    def get_permissions(self):
        return [CanIssuePriceSnapshot()]

    @extend_schema(tags=["Pricing"], summary="Issue a server-authoritative price snapshot for a variant (customer-safe, no client price accepted)", request=IssueVariantPriceSnapshotSerializer, responses={201: OpenApiResponse(description="Snapshot issued"), **_responses(401, 403, 404, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = IssueVariantPriceSnapshotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def _payload(snapshot):
            return {"id": str(snapshot.id), "token": str(snapshot.token), "product_variant_id": str(snapshot.product_variant_id), "unit_amount": str(snapshot.locked_price.amount), "currency": snapshot.locked_price.currency, "expires_at": snapshot.expires_at.isoformat(), "status": snapshot.status.value}

        return protect_with_idempotency(
            request, _actor_id(request), "pricing.issue_variant_price_snapshot", serializer.validated_data,
            operation=lambda: composition.build_issue_variant_price_snapshot(_actor_id(request)).execute(**serializer.validated_data),
            result_to_payload=_payload,
            success_status_code=201,
        )


class PricingSearchView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Pricing"], summary="Search price lists")
    def get(self, request):
        params = parse_pagination(request.query_params)
        query = request.query_params.get("q", "")
        results, total = composition.build_search_pricing().execute(query=query, filters={}, page=params.page, page_size=params.page_size)
        total_pages = max((total + params.page_size - 1) // params.page_size, 1)
        return paginated_response(data=results, pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": total})
