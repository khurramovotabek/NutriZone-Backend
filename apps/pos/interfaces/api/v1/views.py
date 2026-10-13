"""
POS HTTP API views.

Thin per Django Implementation Blueprint §3. No view instantiates a
repository, ORM model, or Application Service class directly outside
`composition.py`, and never mutates a Domain aggregate directly.

**6 real Sale endpoints, 0 honest-501, matching Analytics' own
precedent of being fully real** -- 6 certified Application Services
exist (Phase 3), all wired via `composition.py` (Phase 3's own
disclosed extension). Every view calls a `composition.build_*`
factory, passing `_actor_id(request)` where the factory accepts one
(confirmed via Step 1's exact factory-signature re-verification),
then calls `.execute(...)`.

**`SaleLineItem` has no standalone endpoint anywhere** -- matching its
certified owned-entity status; it is only ever visible nested inside
`SaleSerializer`'s own `line_items` field.

**No list/query endpoint exists for Sale** -- Infrastructure certifies
0 selectors; fabricating one would require a query capability that
does not exist.

**A 7th, new endpoint for the POS Search module**: `SearchView`.
`SearchProduct.execute()` is a pure, read-only query -- it never
mutates a `Sale`, so this view intentionally does not call
`AddLineItem` itself; per the Search module's own Section 8, a
successful resolution returns enough information (`product_id`,
`variant_id`) for a *separate*, subsequent `AddLineItem` call to
proceed, never combining the two operations into one HTTP request.
"""
from __future__ import annotations

import uuid

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.views import APIView

from apps.pos.interfaces.api.v1.permissions import ManageSale, SearchProducts, ViewSale
from apps.pos.interfaces.api.v1.serializers import (
    AddLineItemSerializer, CompleteSaleSerializer, OpenSaleSerializer, PriceResolutionQuerySerializer,
    PriceResolutionResultSerializer, RemoveLineItemSerializer, SaleSerializer, SearchQuerySerializer,
    SearchResultSerializer, VoidSaleSerializer,
)
from apps.pos.infrastructure import composition
from common.responses import success_response
from core.openapi import STANDARD_ERROR_RESPONSES
from core.ratelimit import ScopedRateLimitThrottle


def _responses(*codes: int) -> dict:
    return {code: STANDARD_ERROR_RESPONSES[code] for code in codes}


def _attach_identity(request) -> None:
    request.identity = request.user


def _actor_id(request):
    return getattr(getattr(request, "user", None), "id", None)


class PosThrottle(ScopedRateLimitThrottle):
    scope = "pos.operation"
    limit = 3000
    window_seconds = 3600
    identifier_source = "user"


def _sale_payload(sale) -> dict:
    total = sale.total()
    return {
        "id": str(sale.id), "branch_id": str(sale.branch_id), "cashier_id": str(sale.cashier_id),
        "customer_id": str(sale.customer_id) if sale.customer_id else None, "status": sale.status.value,
        "total_amount": str(total.amount), "total_currency": total.currency,
        "created_at": sale.created_at.isoformat() if sale.created_at else None,
        "completed_at": sale.completed_at.isoformat() if sale.completed_at else None,
        "voided_at": sale.voided_at.isoformat() if sale.voided_at else None,
        "line_items": [{"id": str(li.id), "product_id": str(li.product_id), "quantity": li.quantity.value, "unit_price_amount": str(li.unit_price.amount), "unit_price_currency": li.unit_price.currency} for li in sale.line_items.values()],
    }


# ============================================================
# Sale -- every operation is real
# ============================================================


class SaleListCreateView(APIView):
    """POST is real (`OpenSale`). No GET -- Infrastructure certifies 0 selectors; there is no listing capability to expose."""

    throttle_classes = [PosThrottle]
    permission_classes = [ManageSale]

    @extend_schema(tags=["POS"], summary="Open a new sale", request=OpenSaleSerializer, responses={201: OpenApiResponse(description="Sale opened"), **_responses(401, 403, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = OpenSaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sale = composition.build_open_sale(_actor_id(request)).execute(
            branch_id=serializer.validated_data["branch_id"], cashier_id=serializer.validated_data["cashier_id"], customer_id=serializer.validated_data.get("customer_id"),
        )
        return success_response(data=_sale_payload(sale), status_code=201)


class SaleDetailView(APIView):
    permission_classes = [ViewSale]

    @extend_schema(tags=["POS"], summary="Get a sale by id", responses={200: OpenApiResponse(description="Sale detail"), **_responses(401, 403, 404)})
    def get(self, request, sale_id: str):
        _attach_identity(request)
        sale = composition.build_load_sale().execute(uuid.UUID(sale_id))
        return success_response(data=_sale_payload(sale))


class AddLineItemView(APIView):
    throttle_classes = [PosThrottle]
    permission_classes = [ManageSale]

    @extend_schema(tags=["POS"], summary="Add a line item to a sale", request=AddLineItemSerializer, responses={200: OpenApiResponse(description="Line item added"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request, sale_id: str):
        _attach_identity(request)
        serializer = AddLineItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sale = composition.build_add_line_item(_actor_id(request)).execute(
            sale_id=uuid.UUID(sale_id), product_id=serializer.validated_data["product_id"], quantity=serializer.validated_data["quantity"],
            unit_price_amount=serializer.validated_data["unit_price_amount"], unit_price_currency=serializer.validated_data["unit_price_currency"],
        )
        return success_response(data=_sale_payload(sale))


class RemoveLineItemView(APIView):
    throttle_classes = [PosThrottle]
    permission_classes = [ManageSale]

    @extend_schema(tags=["POS"], summary="Remove a line item from a sale", request=RemoveLineItemSerializer, responses={200: OpenApiResponse(description="Line item removed"), **_responses(401, 403, 404, 409, 422)})
    def delete(self, request, sale_id: str, line_item_id: str):
        _attach_identity(request)
        sale = composition.build_remove_line_item(_actor_id(request)).execute(sale_id=uuid.UUID(sale_id), line_item_id=uuid.UUID(line_item_id))
        return success_response(data=_sale_payload(sale))


class CompleteSaleView(APIView):
    throttle_classes = [PosThrottle]
    permission_classes = [ManageSale]

    @extend_schema(tags=["POS"], summary="Complete a sale", request=CompleteSaleSerializer, responses={200: OpenApiResponse(description="Sale completed"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request, sale_id: str):
        _attach_identity(request)
        sale = composition.build_complete_sale(_actor_id(request)).execute(uuid.UUID(sale_id))
        return success_response(data=_sale_payload(sale))


class VoidSaleView(APIView):
    throttle_classes = [PosThrottle]
    permission_classes = [ManageSale]

    @extend_schema(tags=["POS"], summary="Void a sale", request=VoidSaleSerializer, responses={200: OpenApiResponse(description="Sale voided"), **_responses(401, 403, 404, 409)})
    def post(self, request, sale_id: str):
        _attach_identity(request)
        sale = composition.build_void_sale(_actor_id(request)).execute(uuid.UUID(sale_id))
        return success_response(data=_sale_payload(sale))


# ============================================================
# Search -- new for the POS Search module, real, read-only
# ============================================================


def _search_result_payload(result: dict) -> dict:
    exact_match = None
    if result["exact_match"] is not None:
        exact_match = {"product_id": str(result["exact_match"]["product_id"]), "variant_id": str(result["exact_match"]["variant_id"])}
    return {"mode": result["mode"], "exact_match": exact_match, "results": result["results"], "total_count": result["total_count"]}


class SearchView(APIView):
    """Resolves cashier input (barcode / SKU / free text) via the certified priority cascade. Never mutates a Sale -- a successful exact match returns `product_id`/`variant_id` for a separate, subsequent `AddLineItem` call."""

    permission_classes = [SearchProducts]

    @extend_schema(
        tags=["POS"], summary="Resolve a product by barcode, SKU, or free text",
        description="Automatic priority cascade (barcode -> SKU -> text) when `type` is omitted, matching the certified Search module priority order. An explicit `type` skips the cascade and resolves directly against that strategy only.",
        responses={200: SearchResultSerializer, **_responses(401, 403, 404, 422)},
    )
    def get(self, request):
        _attach_identity(request)
        serializer = SearchQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = composition.build_search_product().execute(
            query=serializer.validated_data["q"], mode=serializer.validated_data.get("type"),
            page=serializer.validated_data["page"], page_size=serializer.validated_data["page_size"],
        )
        return success_response(data=_search_result_payload(result))


# ============================================================
# Pricing -- new for POS Phase 11, exposing Phase 7's ResolveLineItemPrice
# ============================================================


class PriceResolutionView(APIView):
    """Resolves the authoritative price for a product variant via Pricing's own certified `CalculatePrice`. Never mutates a Sale -- a successful resolution returns `Money` for a separate, subsequent `AddLineItem` call, matching `SearchView`'s own identical read-only/mutation-separation pattern.

    **`ManageSale` is reused, not `SearchProducts`** -- pricing resolution exists specifically to feed the `ManageSale`-gated `AddLineItem` call, matching the identical reasoning already applied to that endpoint, rather than the product-discovery concern `SearchProducts` covers.

    **`price_list_id` remains caller-supplied** -- the documented architectural boundary from Phases 7-10: no authoritative mapping from a Sale's branch to a price list exists anywhere in this repository, and this endpoint does not invent one."""

    permission_classes = [ManageSale]

    @extend_schema(
        tags=["POS"], summary="Resolve the authoritative price for a product variant",
        description="Wraps Pricing's own certified CalculatePrice. price_list_id must be supplied by the caller -- no automatic branch-to-price-list resolution exists in this repository (documented architectural boundary, POS Phases 7-10).",
        responses={200: PriceResolutionResultSerializer, **_responses(401, 403, 404, 422)},
    )
    def get(self, request):
        _attach_identity(request)
        serializer = PriceResolutionQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        money = composition.build_resolve_line_item_price().execute(
            price_list_id=serializer.validated_data["price_list_id"], variant_id=serializer.validated_data["variant_id"],
            quantity=serializer.validated_data["quantity"], at=serializer.validated_data.get("at"),
            coupon_code=serializer.validated_data.get("coupon_code"), region=serializer.validated_data.get("region"),
            membership_tier_code=serializer.validated_data.get("membership_tier_code"),
        )
        return success_response(data={"amount": str(money.amount), "currency": money.currency})
