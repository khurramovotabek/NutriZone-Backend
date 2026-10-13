"""
POS API serializers.

Every field name and shape traced directly to the certified
Application `execute()` contract, re-verified fresh this phase --
every write serializer's fields correspond exactly to a real
Application Service's parameters (verified via AST before writing
this file, not assumed).

`SaleLineItemSerializer` is nested-only, matching the established
"owned entity never becomes an independent top-level resource"
pattern already certified in Domain (Phase 1's own explicit
`SaleLineItem` ownership decision) and Infrastructure (Phase 2's own
explicit rule that this entity gets no independent repository,
selector, or top-level admin page) -- there is no standalone
`/sale-line-items/` resource anywhere in this module.

**No `sale_id`/`at` field exists on `OpenSaleSerializer`** -- both are
generated internally by `OpenSale.execute()`, per the certified
Application contract re-verified this phase.
"""
from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from shared.value_objects.money import DEFAULT_CURRENCY

# --- Read shapes -----------------------------------------------------


class SaleLineItemSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    product_id = serializers.CharField(read_only=True)
    quantity = serializers.IntegerField(read_only=True)
    unit_price_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    unit_price_currency = serializers.CharField(read_only=True)


class SaleSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    branch_id = serializers.CharField(read_only=True)
    cashier_id = serializers.CharField(read_only=True)
    customer_id = serializers.CharField(read_only=True, allow_null=True)
    status = serializers.CharField(read_only=True)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total_currency = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True, allow_null=True)
    completed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    voided_at = serializers.DateTimeField(read_only=True, allow_null=True)
    line_items = SaleLineItemSerializer(many=True, read_only=True)


# --- Command / request DTOs -- every field maps 1:1 to a real execute() parameter ---


class OpenSaleSerializer(serializers.Serializer):
    """Maps exactly to `OpenSale.execute(branch_id, cashier_id, customer_id)`."""

    branch_id = serializers.UUIDField()
    cashier_id = serializers.UUIDField()
    customer_id = serializers.UUIDField(required=False, allow_null=True)


class AddLineItemSerializer(serializers.Serializer):
    """Maps exactly to `AddLineItem.execute(sale_id, product_id, quantity, unit_price_amount, unit_price_currency)` -- `sale_id` comes from the URL path, not this body.

    **`min_value=Decimal("0")` on `unit_price_amount` is a deliberate, disclosed addition, not part of the certified Application contract itself**: `shared.value_objects.money.Money.__post_init__` raises a plain `ValueError` for a negative amount, not a `DomainException` -- confirmed directly against the platform's own `common.exceptions.handlers.nutrizone_exception_handler`, which has no case for bare `ValueError` and would let it fall through to a generic, unhelpful 500. This constraint is a structural HTTP-boundary safeguard, entirely within this module's own scope (a serializer field, not a Shared Kernel or global-handler change), converting what would otherwise be an unhandled server error into a clean, expected 422."""

    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    unit_price_amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"))
    unit_price_currency = serializers.CharField(max_length=3, required=False, default=DEFAULT_CURRENCY)


class RemoveLineItemSerializer(serializers.Serializer):
    """No fields -- both `sale_id` and `line_item_id` come from the URL path, matching the identical zero-field command serializer pattern already established by Wallet's/Loyalty's/Reviews'/Chat's/Notifications'/Analytics' own equivalents."""


class CompleteSaleSerializer(serializers.Serializer):
    """No fields -- matches `RemoveLineItemSerializer`'s rationale."""


class VoidSaleSerializer(serializers.Serializer):
    """No fields -- matches `RemoveLineItemSerializer`'s rationale."""


# --- Search (new for the POS Search module) -------------------------------


class SearchQuerySerializer(serializers.Serializer):
    """Query-string input for `GET /pos/search` -- maps to `SearchProduct.execute(query, mode, page, page_size)`. `mode` is optional; when omitted, the certified barcode -> SKU -> text cascade applies.

    **`q`/`type` are deliberately shorter HTTP-facing names than `execute()`'s own `query`/`mode` parameters** -- `q` matches the conventional query-string parameter name for a search endpoint (this task's own Section 7 example: `?q=5901234123457`); `type` matches this task's own Section 7 example (`?type=barcode`). The view maps these explicitly by keyword, not by matching name -- the same deliberate, disclosed pattern already used for Analytics' own `CreateAnalyticsSnapshotSerializer`."""

    q = serializers.CharField(allow_blank=False)
    type = serializers.ChoiceField(choices=["barcode", "sku", "text"], required=False)
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=100, default=20)


class ProductMatchSerializer(serializers.Serializer):
    """The exact-match shape for a resolved barcode/SKU -- deliberately minimal (Section 8 of the Search module's own brief): enough for the frontend to immediately proceed to the existing `AddLineItem` flow, never a duplicated Product representation."""

    product_id = serializers.CharField(read_only=True)
    variant_id = serializers.CharField(read_only=True)


class SearchResultSerializer(serializers.Serializer):
    """The full response envelope for `GET /pos/search` -- `mode` tells the caller which certified strategy resolved the query; `exact_match` is populated only for barcode/sku mode, `results`/`total_count` only for text mode -- never both, matching `SearchProduct.execute()`'s own certified return shape exactly."""

    mode = serializers.ChoiceField(choices=["barcode", "sku", "text"], read_only=True)
    exact_match = ProductMatchSerializer(read_only=True, allow_null=True)
    results = serializers.ListField(read_only=True, allow_null=True)
    total_count = serializers.IntegerField(read_only=True, allow_null=True)


# --- Pricing (new for POS Phase 11 -- HTTP exposure of Phase 7's ResolveLineItemPrice) ---


class PriceResolutionQuerySerializer(serializers.Serializer):
    """Query-string input for `GET /pos/pricing` -- maps exactly to `ResolveLineItemPrice.execute(price_list_id, variant_id, quantity, at, coupon_code, region, membership_tier_code)`, re-verified fresh this phase against live source. `price_list_id` remains caller-supplied -- the documented Phase 7-10 architectural boundary, not something this endpoint resolves automatically."""

    price_list_id = serializers.UUIDField()
    variant_id = serializers.UUIDField()
    quantity = serializers.IntegerField(required=False, default=1, min_value=1)
    at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    coupon_code = serializers.CharField(required=False, allow_null=True, allow_blank=False, default=None)
    region = serializers.CharField(required=False, allow_null=True, allow_blank=False, default=None)
    membership_tier_code = serializers.CharField(required=False, allow_null=True, allow_blank=False, default=None)


class PriceResolutionResultSerializer(serializers.Serializer):
    """Deliberately minimal -- only the final, authoritative `Money` amount/currency, never Pricing's own richer `PriceCalculationResult` (base_price/applied_discounts), matching `PricingResolverAdapter`'s own certified boundary exactly (Phase 7)."""

    amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    currency = serializers.CharField(read_only=True)
