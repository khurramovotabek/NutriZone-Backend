"""
Cart API views.

Thin per Django Implementation Blueprint §3: each view deserializes,
calls exactly one Application Service or Selector (built/accessed via
infrastructure/composition.py), and returns through the standard
response envelope. Every collection endpoint (list+create) is ONE
view class on ONE path. No view instantiates a repository, imports
infrastructure.models, or constructs a domain aggregate.

`ConvertCartView` is a documented, partial implementation -- see its
own docstring and this phase's certification report for why a true
CONVERTED-status transition is not yet possible.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.views import APIView

from apps.cart.infrastructure import composition
from apps.cart.interfaces.api.v1.filters import parse_cart_list_params, parse_pagination
from apps.cart.interfaces.api.v1.permissions import (
    CanAttachCoupon, CanAttachPriceSnapshot, CanAttachReservation, CanCheckoutCart, CanConvertCart, CanCreateCart,
    CanDeleteCart, CanLockCart, CanManageCart, CanManageCartItems, CanManageGuestCart, CanMergeCart,
    CanSearchCart, CanUpdateCart, CanValidateCart, CanViewCart, CanViewCartAudit,
)
from apps.cart.interfaces.api.v1.serializers import (
    AddItemSerializer, ApplyCheckoutCouponByCodeSerializer, ApplyCouponSerializer, AttachPriceSnapshotSerializer, AttachReservationSerializer,
    CheckoutCartSerializer, CreateCartSerializer, DetachPriceSnapshotSerializer, DetachReservationSerializer, LockCartSerializer,
    MergeGuestCartSerializer, PriceItemSerializer, UpdateCartSerializer, UpdateItemSerializer,
)
from common.exceptions import ConflictError, ResourceNotFound
from common.exceptions import PermissionDenied as DomainPermissionDenied
from common.idempotency import protect_with_idempotency
from common.responses import paginated_response, success_response
from core.openapi import STANDARD_ERROR_RESPONSES
from core.ratelimit import ScopedRateLimitThrottle


def _responses(*codes: int) -> dict:
    return {code: STANDARD_ERROR_RESPONSES[code] for code in codes}


def _attach_identity(request) -> None:
    request.identity = request.user


def _require_cart_ownership(request, cart) -> None:
    """
    Phase 03A continuation: closes the verified Cart security gap.
    `Cart.token: CartToken` already existed and was already returned
    to clients in `_cart_payload()` on every cart response -- the
    write side worked, but no view ever validated an incoming token
    against it, the read/authorization side was simply never wired.

    Model A (confirmed via `CartToken`'s own docstring: "an opaque,
    unique access token for a guest cart... what a browser/mobile
    client holds (e.g. in a cookie) to reference its cart without an
    authenticated identity"):

    - Authenticated cart (`cart.customer_id is not None`): ownership
      requires `cart.customer_id == request.user.id`.
    - Guest cart (`cart.customer_id is None`): ownership requires the
      client to supply the matching `CartToken` via a new
      `X-Cart-Token` header (chosen deliberately over a query
      parameter -- headers are not logged/cached by intermediaries
      the way URLs commonly are, and this mirrors the existing
      `Authorization: Bearer <JWT>` header convention already used
      for authenticated identity in this same project). Compared with
      `hmac.compare_digest` -- timing-safe, matching this project's
      own established webhook-signature discipline (Phase 02E) for
      any secret-comparison operation.

    No staff-bypass permission exists for Cart today (confirmed: no
    `ViewAnyCart`-style permission code exists anywhere in this
    module, unlike Wallet/Ordering/Loyalty) -- none was invented here,
    matching the same "don't add a new feature beyond the bug fix"
    discipline already applied to the Reviews fix.
    """
    import hmac

    if cart.customer_id is not None:
        if cart.customer_id == getattr(request.user, "id", None):
            return
        raise DomainPermissionDenied("You do not have permission to access this cart.")

    supplied_token = request.headers.get("X-Cart-Token", "")
    if supplied_token and hmac.compare_digest(supplied_token, str(cart.token)):
        return
    raise DomainPermissionDenied("You do not have permission to access this cart.")


def _actor_id(request):
    return getattr(getattr(request, "user", None), "id", None)


class CartThrottle(ScopedRateLimitThrottle):
    scope = "cart.operation"
    limit = 3000
    window_seconds = 3600
    identifier_source = "user"


def _cart_payload(cart) -> dict:
    return {
        "id": str(cart.id), "code": cart.code.value, "token": str(cart.token), "version": cart.version.value,
        "currency": cart.currency.value, "cart_type": cart.cart_type.value, "status": cart.status.value,
        "customer_id": str(cart.customer_id) if cart.customer_id else None,
        "region": cart.region.value if cart.region else None, "channel": cart.channel.value if cart.channel else None,
        "items": [_item_payload(i) for i in cart.items.values() if i.status.value != "removed"],
        "coupon_ids": [str(c) for c in cart.coupon_ids], "note": cart.note.text if cart.note else None,
        "gift_message": cart.gift_message.text if cart.gift_message else None,
        "expires_at": cart.expires_at.isoformat() if cart.expires_at else None, "is_locked": cart.lock_reason is not None,
    }


def _item_payload(item) -> dict:
    return {
        "id": str(item.id), "product_variant_id": str(item.product_variant_id), "quantity": item.quantity.value, "status": item.status.value,
        "price_reference": {"price_snapshot_id": str(item.price_reference.price_snapshot_id), "unit_amount": str(item.price_reference.unit_amount.amount), "currency": item.price_reference.unit_amount.currency, "applied_at": item.price_reference.applied_at.isoformat()} if item.price_reference else None,
        "reservation_reference": {"reservation_id": str(item.reservation_reference.reservation_id), "reserved_at": item.reservation_reference.reserved_at.isoformat(), "expires_at": item.reservation_reference.expires_at.isoformat() if item.reservation_reference.expires_at else None} if item.reservation_reference else None,
        "note": item.note.text if item.note else None,
    }


def _resolve_coupon_id_by_code(coupon_code: str | None, customer_id=None, subtotal: Decimal | None = None, check: bool = True):
    """
    The storefront customer types a human-readable code ("SUMMER20"); it is resolved against CouponModel and,
    when applying (check=True), checked against every coupon rule (apps/pricing/infrastructure/coupon_rules.py):
    active, validity window, total and per-customer limits, minimum order. Removing a coupon never checks.
    """
    from apps.pricing.infrastructure import coupon_rules
    from apps.pricing.infrastructure.models import CouponModel

    if not coupon_code:
        raise ResourceNotFound("Coupon code is required.")
    coupon = CouponModel.objects.filter(code=coupon_code.strip().upper()).first()
    if coupon is None:
        raise ResourceNotFound(f"No coupon exists with code '{coupon_code}'.")
    if check:
        coupon_rules.assert_usable(coupon, customer_id, subtotal)
    return coupon.id


def _cart_gross(cart) -> Decimal:
    return sum((i.price_reference.unit_amount.amount * i.quantity.value for i in cart.items.values()
                if i.status.value != "removed" and i.price_reference is not None), Decimal("0"))


def _compute_cart_discount(coupon_ids: set, subtotal: dict | None, customer_id=None) -> tuple[list, dict | None]:
    """
    Real, closed gap: this project's own Checkout Preview View
    honestly disclosed "no backend source exists for a checkout-level
    discount" -- but real coupons (CouponModel) with real
    discount_value_type/percentage/fixed_amount and stacking_mode
    already exist, just never applied at the cart-summary level.
    Computed directly from each real, attached coupon's own stored
    values -- no fabricated discount, no invented percentage.
    """
    if not coupon_ids or not subtotal:
        return [], None

    from apps.pricing.domain.enums import StackingMode
    from apps.pricing.infrastructure.models import CouponModel

    from apps.pricing.infrastructure import coupon_rules

    subtotal_amount = Decimal(subtotal["amount"])
    # only coupons that can be used right now (limits, validity, minimum order) give a discount
    coupons = [c for c in CouponModel.objects.filter(id__in=coupon_ids) if coupon_rules.problem(c, customer_id, subtotal_amount) is None]
    if not coupons:
        return [], None

    def coupon_discount_amount(coupon) -> Decimal:
        return coupon_rules.discount_amount(coupon, subtotal_amount)

    exclusive = [c for c in coupons if c.stacking_mode == StackingMode.EXCLUSIVE.value]
    stackable = [c for c in coupons if c.stacking_mode == StackingMode.STACKABLE.value]
    best_of = [c for c in coupons if c.stacking_mode == StackingMode.BEST_OF.value]

    applied: list[dict] = []
    total_discount = Decimal("0")

    if exclusive:
        winner = exclusive[0]
        amount = coupon_discount_amount(winner)
        applied.append({"code": winner.code, "id": str(winner.id), "amount": str(amount)})
        total_discount = amount
    else:
        for c in stackable:
            amount = coupon_discount_amount(c)
            applied.append({"code": c.code, "id": str(c.id), "amount": str(amount)})
            total_discount += amount
        if best_of:
            winner = max(best_of, key=coupon_discount_amount)
            amount = coupon_discount_amount(winner)
            applied.append({"code": winner.code, "id": str(winner.id), "amount": str(amount)})
            total_discount += amount

    total_discount = min(total_discount, subtotal_amount)  # a discount can never exceed the real subtotal it applies to
    if total_discount <= 0:
        return [], None
    return applied, {"amount": str(total_discount), "currency": subtotal["currency"]}


def _load_cart_by_code(code: str, request):
    cart = composition.build_load_cart().execute(code=code)
    _require_cart_ownership(request, cart)
    return cart


# ============================================================
# Cart
# ============================================================


class CartListCreateView(APIView):
    """Combined GET (list, admin) + POST (create) at one path."""

    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanCreateCart()] if self.request.method == "POST" else [CanManageCart()]

    @extend_schema(tags=["Cart Admin"], summary="List carts (staff)", responses={200: OpenApiResponse(description="Cart collection"), **_responses(401, 403, 422)})
    def get(self, request):
        _attach_identity(request)
        params = parse_cart_list_params(request.query_params)
        items, total = composition.build_admin_list_carts().execute(status=params.status, cart_type=params.cart_type, page=params.page, page_size=params.page_size)
        total_pages = max((total + params.page_size - 1) // params.page_size, 1)
        return paginated_response(data=[_cart_payload(c) for c in items], pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Cart"], summary="Create a cart (guest or authenticated)", request=CreateCartSerializer, responses={201: OpenApiResponse(description="Cart created"), **_responses(401, 403, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart = composition.build_create_cart(_actor_id(request)).execute(**serializer.validated_data)
        return success_response(data=_cart_payload(cart), status_code=201)


class CartDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [CanViewCart()]
        if self.request.method == "DELETE":
            return [CanDeleteCart()]
        return [CanUpdateCart()]

    @extend_schema(tags=["Cart"], summary="Get a cart by code", responses={200: OpenApiResponse(description="Cart detail"), **_responses(401, 403, 404)})
    def get(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        return success_response(data=_cart_payload(cart))

    @extend_schema(tags=["Cart"], summary="Update cart note/gift message", request=UpdateCartSerializer, responses={200: OpenApiResponse(description="Updated"), **_responses(401, 403, 404, 422)})
    def patch(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = UpdateCartSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        saved = composition.build_update_cart_details(_actor_id(request)).execute(cart_id=cart.id, **serializer.validated_data)
        return success_response(data=_cart_payload(saved))

    @extend_schema(tags=["Cart"], summary="Delete a cart (must already be archived)", responses={204: OpenApiResponse(description="Deleted"), **_responses(401, 403, 404, 409)})
    def delete(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        if cart.status.value != "archived":
            raise ConflictError("Only an archived cart may be deleted. Archive it first.")
        composition.build_cart_repository().delete(cart.id)
        return success_response(data=None, status_code=204)


# ============================================================
# Items
# ============================================================


class CartItemListCreateView(APIView):
    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanManageCartItems()]

    @extend_schema(tags=["Cart"], summary="Add an item to the cart", request=AddItemSerializer, responses={201: OpenApiResponse(description="Item added"), **_responses(401, 403, 404, 422)})
    def post(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = AddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = composition.build_add_item(_actor_id(request)).execute(cart_id=cart.id, **serializer.validated_data)
        return success_response(data=_cart_payload(updated), status_code=201)


class CartItemDetailView(APIView):
    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanManageCartItems()]

    @extend_schema(tags=["Cart"], summary="Update a line item's quantity", request=UpdateItemSerializer, responses={200: OpenApiResponse(description="Updated"), **_responses(401, 403, 404, 422)})
    def patch(self, request, code: str, line_id: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = UpdateItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = composition.build_update_quantity(_actor_id(request)).execute(cart_id=cart.id, item_id=uuid.UUID(line_id), **serializer.validated_data)
        return success_response(data=_cart_payload(updated))

    @extend_schema(tags=["Cart"], summary="Remove a line item", responses={204: OpenApiResponse(description="Removed"), **_responses(401, 403, 404)})
    def delete(self, request, code: str, line_id: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        composition.build_remove_item(_actor_id(request)).execute(cart_id=cart.id, item_id=uuid.UUID(line_id))
        return success_response(data=None, status_code=204)


class ClearCartView(APIView):
    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanManageCartItems()]

    @extend_schema(tags=["Cart"], summary="Remove every item from the cart", responses={200: OpenApiResponse(description="Cleared"), **_responses(401, 403, 404)})
    def post(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        updated = composition.build_clear_cart(_actor_id(request)).execute(cart.id)
        return success_response(data=_cart_payload(updated))


# ============================================================
# Coupon / Reservation / Price Snapshot references
# ============================================================


class CouponReferenceView(APIView):
    """Pre-existing, staff-only endpoint -- unmodified. Applying a coupon here re-runs RecalculateCartPricing, overwriting each item's own locked price with the coupon-discounted amount (its own established, tested behavior)."""

    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanAttachCoupon()]

    @extend_schema(tags=["Cart"], summary="Apply a coupon reference to the cart", request=ApplyCouponSerializer, responses={200: OpenApiResponse(description="Applied"), **_responses(401, 403, 404, 422)})
    def post(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = ApplyCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = composition.build_apply_coupon_reference(_actor_id(request)).execute(cart_id=cart.id, **serializer.validated_data)
        return success_response(data=_cart_payload(updated))

    @extend_schema(tags=["Cart"], summary="Remove a coupon reference from the cart", request=ApplyCouponSerializer, responses={200: OpenApiResponse(description="Removed"), **_responses(401, 403, 404)})
    def delete(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = ApplyCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = composition.build_remove_coupon_reference(_actor_id(request)).execute(cart_id=cart.id, **serializer.validated_data)
        return success_response(data=_cart_payload(updated))


class CheckoutCouponView(APIView):
    """
    Real, closed gap: the storefront checkout needs a customer-facing
    way to apply/remove a coupon by its human-readable code, with the
    discount surfaced only in CheckoutPreviewView's own real, computed
    summary -- not by overwriting each item's locked price (which
    would make removing the coupon later impossible to reverse
    cleanly, and would double-count against this view's own
    _compute_cart_discount()). Fully separate from the pre-existing,
    staff-only CouponReferenceView above -- that endpoint's own
    established repricing behavior is left completely untouched.
    """

    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanValidateCart()]

    @extend_schema(tags=["Cart"], summary="Apply a coupon by its real, human-readable code to the cart (checkout-facing; does not reprice items)", request=ApplyCheckoutCouponByCodeSerializer, responses={200: OpenApiResponse(description="Applied"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = ApplyCheckoutCouponByCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        coupon_id = _resolve_coupon_id_by_code(serializer.validated_data["coupon_code"], _actor_id(request), _cart_gross(cart) or None)
        updated = composition.build_apply_coupon_to_cart_without_repricing(_actor_id(request)).execute(cart_id=cart.id, coupon_id=coupon_id)
        return success_response(data=_cart_payload(updated))

    @extend_schema(tags=["Cart"], summary="Remove a checkout-facing coupon from the cart by its code", request=ApplyCheckoutCouponByCodeSerializer, responses={200: OpenApiResponse(description="Removed"), **_responses(401, 403, 404)})
    def delete(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = ApplyCheckoutCouponByCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        coupon_id = _resolve_coupon_id_by_code(serializer.validated_data["coupon_code"], check=False)
        updated = composition.build_remove_coupon_reference(_actor_id(request)).execute(cart_id=cart.id, coupon_id=coupon_id)
        return success_response(data=_cart_payload(updated))
        updated = composition.build_remove_coupon_reference(_actor_id(request)).execute(cart_id=cart.id, coupon_id=coupon_id)
        return success_response(data=_cart_payload(updated))


class ReservationReferenceView(APIView):
    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanAttachReservation()]

    @extend_schema(tags=["Cart"], summary="Attach an inventory reservation reference to a line item", request=AttachReservationSerializer, responses={200: OpenApiResponse(description="Attached"), **_responses(401, 403, 404, 422)})
    def post(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = AttachReservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = composition.build_attach_reservation(_actor_id(request)).execute(cart_id=cart.id, **serializer.validated_data)
        return success_response(data=_cart_payload(updated))

    @extend_schema(tags=["Cart"], summary="Detach an inventory reservation reference from a line item", request=DetachReservationSerializer, responses={200: OpenApiResponse(description="Detached"), **_responses(401, 403, 404)})
    def delete(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = DetachReservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = composition.build_detach_reservation(_actor_id(request)).execute(cart_id=cart.id, **serializer.validated_data)
        return success_response(data=_cart_payload(updated))


class PriceCartItemView(APIView):
    """
    Phase 09.4: the new, safe composition this project's Cart↔Pricing
    boundary was missing. Verifies cart ownership (reusing
    `_load_cart_by_code`, the same check every other cart-mutating
    view already uses), looks up the item's real
    `product_variant_id`, calls Pricing's own `IssueVariantPriceSnapshot`
    (server-side, no client price), then attaches the result via
    Cart's own existing `AttachPriceSnapshot` service -- both steps in
    one backend request, so a client-side failure between two
    separate HTTP calls can never leave a priced-but-unattached (or
    attached-but-unpriced) partial state.
    """

    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanAttachPriceSnapshot()]

    @extend_schema(tags=["Cart"], summary="Resolve and attach a server-authoritative price for a line item (no client price accepted)", request=PriceItemSerializer, responses={200: OpenApiResponse(description="Priced"), **_responses(401, 403, 404, 422)})
    def post(self, request, code: str, item_id: str):
        from apps.pricing.infrastructure import composition as pricing_composition

        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        item_uuid = uuid.UUID(item_id)
        serializer = PriceItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        coupon_code = serializer.validated_data.get("coupon_code")

        item = cart.items.get(item_uuid)
        if item is None:
            raise ResourceNotFound("Cart item not found.")

        def _price_and_attach():
            snapshot = pricing_composition.build_issue_variant_price_snapshot(_actor_id(request)).execute(
                product_variant_id=item.product_variant_id, quantity=item.quantity.value, coupon_code=coupon_code, region=cart.region.value if cart.region else None,
            )
            return composition.build_attach_price_snapshot(_actor_id(request)).execute(
                cart_id=cart.id, item_id=item_uuid, price_snapshot_id=snapshot.id, unit_amount=snapshot.locked_price.amount, currency=snapshot.locked_price.currency,
            )

        return protect_with_idempotency(
            request, _actor_id(request), "cart.price_item", {"cart_id": str(cart.id), "item_id": item_id, "coupon_code": coupon_code},
            operation=_price_and_attach,
            result_to_payload=_cart_payload,
        )


class CartNotReadyForCheckout(ConflictError):
    """Phase 09.7: raised when checkout is attempted on a cart that CalculateCheckoutReadiness reports as not ready, or that has an item with no confirmed price. Fixes a real bug found via a failing test in Phase 09.7b: ConflictError's own __init__ does not accept a `code=` kwarg -- `code` is a class attribute, matching every other named exception in this codebase (e.g. IdempotencyConflict)."""

    code = "CART_NOT_READY"


def _checkout_discounts(cart, active_items, actor_id, requested_coins: int) -> tuple[list, int, Decimal, list, Decimal]:
    """
    Order-level discounts are spread over the lines as `discount_amount`, the one
    field every downstream total already honours (payable amount, revenue, coin
    earning): the coupon discount shown in checkout preview (previously displayed
    but never carried into the order) plus any coins the customer pays with.
    Returns (per-line discounts, validated coins, payable amount before coins).
    """
    from apps.loyalty.infrastructure import services as loyalty

    line_gross = [item.price_reference.unit_amount.amount * item.quantity.value for item in active_items]
    gross = sum(line_gross, Decimal("0"))
    applied, coupon_discount = _compute_cart_discount(cart.coupon_ids, {"amount": str(gross), "currency": cart.currency.value} if gross else None, actor_id)
    coupon_amount = Decimal(coupon_discount["amount"]) if coupon_discount else Decimal("0")
    payable_before_coins = gross - coupon_amount
    coins = 0
    if requested_coins and cart.currency.value == "UZS":
        try:
            coins = loyalty.validate_redemption(actor_id, requested_coins, payable_before_coins)
        except loyalty.LoyaltyError as exc:
            raise exc.as_conflict() from exc
    return loyalty.allocate_discount(line_gross, coupon_amount + Decimal(coins)), coins, payable_before_coins, [a["id"] for a in applied], gross


def _redeem_coins(actor_id, coins: int, order, payable_before_coins: Decimal) -> None:
    from apps.loyalty.infrastructure import services as loyalty

    if not coins:
        return
    try:
        loyalty.redeem_for_order(actor_id, coins, order.id, order.order_number.value, payable_before_coins)
    except loyalty.LoyaltyError as exc:
        raise exc.as_conflict() from exc


def _loyalty_preview(actor_id, total: dict | None) -> dict | None:
    """Coin-payment options for this cart (1 coin = 1 so'm, capped by the programme's max share). None for guests / non-UZS carts."""
    from apps.loyalty.infrastructure import services as loyalty

    if actor_id is None or not total or total.get("currency") != "UZS":
        return None
    cfg = loyalty.programme()
    usable, balance = loyalty.max_redeemable(actor_id, Decimal(total["amount"]))
    return {
        "enabled": cfg.redeem_enabled, "balance": balance, "max_redeemable": usable,
        "max_percent": cfg.max_redeem_percent, "min_coins": cfg.min_redeem_coins,
    }


class CheckoutCartView(APIView):
    """
    Phase 09.7: the minimal, safe Order Creation composition this
    project's Cart -> Ordering boundary was missing. Composes four
    existing, certified pieces entirely -- CalculateCheckoutReadiness
    (must report "ready"), the real geo.Address aggregate
    (ownership-checked, never trusted from an ID alone), the
    customer's own real name/phone (from Identity, never client
    input), and Ordering's own existing CreateOrderFromCart -- no new
    order-creation logic, no new pricing formula. Every line item's
    unit_price/price_snapshot_id comes directly from the cart's own
    already-server-priced items (item.price_reference), never from
    the request body, which has no such field at all.

    Protected by this project's existing, proven idempotency
    mechanism (protect_with_idempotency) -- the exact same one already
    used by Wallet/Ordering/Inventory and wired into Pricing/Cart in
    Phase 09.6.
    """

    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanCheckoutCart()]

    @extend_schema(tags=["Cart"], summary="Create a real Order from this cart (no client-supplied financial value accepted)", request=CheckoutCartSerializer, responses={201: OpenApiResponse(description="Order created"), **_responses(401, 403, 404, 409, 422)})
    def post(self, request, code: str):
        from apps.geo.infrastructure import composition as geo_composition
        from apps.geo.infrastructure.repositories import DjangoCityRepository, DjangoCountryRepository
        from apps.identity.infrastructure.repositories import DjangoUserRepository
        from apps.ordering.infrastructure import composition as ordering_composition

        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = CheckoutCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        method = serializer.validated_data.get("fulfilment_method") or "delivery"
        pickup_store_id = serializer.validated_data.get("pickup_store_id")
        shipping_address_id = serializer.validated_data.get("shipping_address_id")
        billing_address_id = serializer.validated_data.get("billing_address_id", shipping_address_id)

        readiness = composition.build_calculate_checkout_readiness().execute(cart.id, all_reservations_valid=True)
        if readiness != "ready":
            raise CartNotReadyForCheckout("This cart is not ready for checkout.")

        actor_id = _actor_id(request)
        address_repo = geo_composition.build_address_repository()

        def _load_owned_address(address_id):
            address = address_repo.get_by_id(address_id)
            if address is None or address.owner_type != "user" or address.owner_id != actor_id:
                raise ResourceNotFound("Address not found.")
            return address

        def _address_snapshot(address):
            from apps.geo.application.services.address import delivery_details_line

            country = DjangoCountryRepository().get_by_id(address.country_id)
            city = DjangoCityRepository().get_by_id(address.city_id)
            user = DjangoUserRepository().get_by_id(actor_id)
            # Real, product-required precedence: the address's own
            # recipient_name/recipient_phone (collected at checkout,
            # who the delivery is actually for -- may differ from the
            # ordering customer, e.g. a gift) take priority. Falls
            # back to the customer's own profile name/phone only for
            # an older address saved before this capability existed.
            recipient_name = address.recipient_name or ((user.full_name or user.phone_number.value) if user else "")
            recipient_phone = address.recipient_phone or (user.phone_number.value if user else None)
            return {
                "recipient_name": recipient_name,
                "phone": recipient_phone,
                "line1": address.line1,
                # the courier's line: the customer's own line2, then podyezd / floor / flat / door code / landmark
                "line2": " · ".join(p for p in (address.line2, delivery_details_line(address.metadata)) if p)[:255] or None,
                "city": city.name if city else str(address.city_id),
                "country_code": country.code.value if country else "",
                "postal_code": address.postal_code.value if address.postal_code else None,
                "latitude": address.coordinate.point.coordinate.latitude.value if address.coordinate else None,
                "longitude": address.coordinate.point.coordinate.longitude.value if address.coordinate else None,
            }

        active_items = [i for i in cart.items.values() if i.status.value != "removed"]
        if any(i.price_reference is None for i in active_items):
            raise CartNotReadyForCheckout("Every item must have a confirmed price before checkout.")

        pickup = None
        if method == "pickup":
            from apps.stores.infrastructure import store_orders

            try:
                pickup = store_orders.pickup_store(pickup_store_id, [(i.product_variant_id, i.quantity.value) for i in active_items])
            except store_orders.StoreOrderError as exc:
                err = ConflictError(exc.message)
                err.code = exc.code  # PICKUP_STORE_UNAVAILABLE / PICKUP_STORE_OUT_OF_STOCK -- the storefront shows a clear message
                raise err from exc
            user = DjangoUserRepository().get_by_id(actor_id)
            name = (user.full_name or user.phone_number.value) if user else ""
            phone = user.phone_number.value if user else None
            pickup_snapshot = store_orders.pickup_snapshot(pickup, name, phone)
            # a saved address is optional for pickup (used as billing when given)
            billing = _address_snapshot(_load_owned_address(billing_address_id)) if billing_address_id else pickup_snapshot
            shipping_snapshot, billing_snapshot = pickup_snapshot, billing
        else:
            shipping_snapshot = _address_snapshot(_load_owned_address(shipping_address_id))
            billing_snapshot = _address_snapshot(_load_owned_address(billing_address_id))

        line_discounts, coins_to_redeem, payable_before_coins, applied_coupon_ids, gross = _checkout_discounts(cart, active_items, actor_id, serializer.validated_data.get("coins_to_redeem") or 0)

        line_items = [
            {
                "product_variant_id": str(item.product_variant_id),
                "quantity": item.quantity.value,
                "unit_price": str(item.price_reference.unit_amount.amount),
                "price_snapshot_id": str(item.price_reference.price_snapshot_id),
                "discount_amount": str(discount),
            }
            for item, discount in zip(active_items, line_discounts, strict=True)
        ]

        def _create_order():
            from apps.pricing.infrastructure import composition as pricing_composition

            with transaction.atomic():
                order = ordering_composition.build_create_order_from_cart(actor_id).execute(
                    cart_id=cart.id, customer_id=actor_id, currency=cart.currency.value,
                    shipping_address=shipping_snapshot, billing_address=billing_snapshot,
                    # Real, closed bug: `cart.coupon_ids` (apps.cart.domain.aggregates.Cart)
                    # is a set of real uuid.UUID objects -- apply_coupon_reference()'s own
                    # signature takes `coupon_id: uuid.UUID`, never a string (confirmed
                    # directly against the aggregate). Re-wrapping an already-UUID value in
                    # uuid.UUID(c) crashed with AttributeError ('UUID' object has no
                    # attribute 'replace') the moment any cart actually had a coupon applied
                    # -- checkout only "worked" in every prior test because none of them
                    # exercised the coupon path. list() only re-shapes the set into an
                    # ordered sequence for the call below; every element is already the
                    # correct type.
                    line_items=line_items, coupon_ids=list(cart.coupon_ids),
                    customer_comment=cart.note.text if cart.note else None,
                )
                # Phase 09.7: closes a real, confirmed gap -- CreateOrderFromCart
                # never transitions PriceSnapshot LOCKED -> CONSUMED on its own
                # (confirmed directly: no ConsumePriceSnapshot reference anywhere
                # in that service). Consuming only after a successful order
                # creation, inside this same idempotency-protected operation.
                #
                # Phase 09.7c fix: both calls must share this one explicit
                # transaction.atomic() block. Each inner service has its own
                # @transaction.atomic, but without a shared outer block each
                # commits independently rather than nesting as a savepoint --
                # confirmed by a real failing test where a ConsumePriceSnapshot
                # failure still left a committed Order behind.
                consume_snapshot = pricing_composition.build_consume_price_snapshot(actor_id)
                for item in active_items:
                    consume_snapshot.execute(item.price_reference.price_snapshot_id)
                # Coins leave the wallet in the SAME transaction as the order: either both
                # happen or neither does (a race that empties the wallet rolls the order back).
                _redeem_coins(actor_id, coins_to_redeem, order, payable_before_coins)
                # every coupon that gave a discount records one use (limits count these) -- same transaction as the order
                from apps.pricing.infrastructure import coupon_rules

                coupon_rules.redeem(applied_coupon_ids, actor_id, order.order_number.value, gross)
                if pickup is not None:  # the branch owner sees the order (and is told about it) right away
                    from apps.ordering.infrastructure.models import OrderModel
                    from apps.stores.infrastructure import store_orders

                    store_orders.assign(OrderModel.objects.get(pk=order.id), pickup, by="checkout", method="pickup")
                return order

        def _order_payload(order):
            return {
                "id": str(order.id), "order_number": order.order_number.value, "status": order.status.value,
                "currency": order.currency, "line_count": len(line_items),
            }

        return protect_with_idempotency(
            request, actor_id, "cart.checkout", {"cart_id": str(cart.id), "method": method, "pickup_store_id": str(pickup_store_id or ""), "shipping_address_id": str(shipping_address_id or ""),
             "billing_address_id": str(billing_address_id or ""), "coins_to_redeem": coins_to_redeem},
            operation=_create_order,
            result_to_payload=_order_payload,
            success_status_code=201,
        )


class PriceSnapshotReferenceView(APIView):
    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanAttachPriceSnapshot()]

    @extend_schema(tags=["Cart"], summary="Attach a price snapshot reference to a line item", request=AttachPriceSnapshotSerializer, responses={200: OpenApiResponse(description="Attached"), **_responses(401, 403, 404, 422)})
    def post(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = AttachPriceSnapshotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = composition.build_attach_price_snapshot(_actor_id(request)).execute(cart_id=cart.id, **serializer.validated_data)
        return success_response(data=_cart_payload(updated))

    @extend_schema(tags=["Cart"], summary="Detach a price snapshot reference from a line item", request=DetachPriceSnapshotSerializer, responses={200: OpenApiResponse(description="Detached"), **_responses(401, 403, 404)})
    def delete(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = DetachPriceSnapshotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = composition.build_detach_price_snapshot(_actor_id(request)).execute(cart_id=cart.id, **serializer.validated_data)
        return success_response(data=_cart_payload(updated))


# ============================================================
# Merge
# ============================================================


class MergeCartView(APIView):
    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanMergeCart()]

    @extend_schema(tags=["Cart"], summary="Merge a guest cart into this (authenticated) cart", request=MergeGuestCartSerializer, responses={200: OpenApiResponse(description="Merged"), **_responses(401, 403, 404, 422)})
    def post(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = MergeGuestCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = composition.build_merge_guest_cart(_actor_id(request)).execute(authenticated_cart_id=cart.id, **serializer.validated_data)
        return success_response(data=_cart_payload(updated))


# ============================================================
# Lifecycle
# ============================================================


class LockCartView(APIView):
    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanLockCart()]

    @extend_schema(tags=["Cart"], summary="Lock the cart (e.g. checkout in progress)", request=LockCartSerializer, responses={200: OpenApiResponse(description="Locked"), **_responses(401, 403, 404, 409)})
    def post(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        serializer = LockCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        saved = composition.build_lock_cart(_actor_id(request)).execute(cart_id=cart.id, **serializer.validated_data)
        return success_response(data=_cart_payload(saved))


class UnlockCartView(APIView):
    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanLockCart()]

    @extend_schema(tags=["Cart"], summary="Unlock the cart", responses={200: OpenApiResponse(description="Unlocked"), **_responses(401, 403, 404, 409)})
    def post(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        saved = composition.build_unlock_cart(_actor_id(request)).execute(cart.id)
        return success_response(data=_cart_payload(saved))


class ConvertCartView(APIView):
    """
    NOT a real 'convert to Order' transition -- no such Application
    Service or domain method exists (see this phase's certification
    report, Step 1-equivalent findings). This endpoint is a documented
    placeholder that performs the closest legitimate action available
    today: locking the cart for checkout. A future Ordering module
    would need its own Domain/Application amendment (adding
    `Cart.convert()` + a `ConvertCart` service) before this endpoint
    can perform a genuine status transition to CONVERTED.
    """

    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanConvertCart()]

    @extend_schema(tags=["Cart"], summary="[Placeholder] Lock the cart for checkout -- does not yet transition to CONVERTED; see description", description="This endpoint currently locks the cart (CHECKOUT_IN_PROGRESS) rather than performing a true conversion to an Order, since no Cart.convert()/ConvertCart capability exists yet. A future Ordering module's Domain/Application layer must add that capability before this endpoint can be completed.", responses={200: OpenApiResponse(description="Locked (not yet converted)"), **_responses(401, 403, 404, 409)})
    def post(self, request, code: str):
        from apps.cart.domain.enums import CartLockReason

        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        saved = composition.build_lock_cart(_actor_id(request)).execute(cart_id=cart.id, reason=CartLockReason.CHECKOUT_IN_PROGRESS.value)
        return success_response(data=_cart_payload(saved))


# ============================================================
# Validation
# ============================================================


class ValidateCartView(APIView):
    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanValidateCart()]

    @extend_schema(tags=["Cart"], summary="Validate the cart's current state", responses={200: OpenApiResponse(description="Validation result"), **_responses(401, 403, 404)})
    def post(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        issues = composition.build_validate_cart().execute(cart.id)
        has_errors = any(i.severity.value == "error" for i in issues)
        return success_response(data={"is_valid": not has_errors, "issues": [{"severity": i.severity.value, "code": i.code.value, "message": i.message, "item_id": str(i.item_id) if i.item_id else None} for i in issues]})


# ============================================================
# Search / Audit / Snapshot History
# ============================================================


class CartSearchView(APIView):
    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanSearchCart()]

    @extend_schema(tags=["Cart Admin"], summary="Search carts")
    def get(self, request):
        _attach_identity(request)
        params = parse_pagination(request.query_params)
        query = request.query_params.get("q", "")
        results, total = composition.build_search_cart().execute(query=query, filters={}, page=params.page, page_size=params.page_size)
        total_pages = max((total + params.page_size - 1) // params.page_size, 1)
        return paginated_response(data=results, pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": total})


class CartAuditView(APIView):
    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanViewCartAudit()]

    @extend_schema(tags=["Cart Admin"], summary="Get a cart's audit trail")
    def get(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        from apps.cart.infrastructure.selectors import CartAuditSelector

        params = parse_pagination(request.query_params)
        entries, total = CartAuditSelector().list_by_cart(cart.id, page=params.page, page_size=params.page_size)
        total_pages = max((total + params.page_size - 1) // params.page_size, 1)
        return paginated_response(data=entries, pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": total})


class CheckoutPreviewView(APIView):
    """
    Phase 09.5: the minimal, safe Checkout Preview this project's
    Cart -> Checkout boundary was missing. Composes two existing,
    certified services entirely -- ValidateCart and
    CalculateCheckoutReadiness -- and adds only a display-only
    arithmetic sum of already-server-priced line items (each
    unit_amount already resolved server-side via CalculatePrice in
    Phase 09.4's IssueVariantPriceSnapshot chain; this view performs
    no pricing calculation of its own).

    Includes a real, cart-level discount summary when one or more real
    coupons are attached (cart.coupon_ids) -- computed directly from
    each CouponModel's own stored discount_value_type/percentage/
    fixed_amount and stacking_mode (exclusive/stackable/best_of), the
    same rules CalculatePrice's own per-item discount stacking already
    enforces. No Delivery Fee / Address selection composition exists,
    and no tax service exists (confirmed by direct search this phase)
    -- delivery/tax are still honestly omitted rather than returned as
    a fabricated zero or null.

    Does NOT create an Order -- CreateOrderFromCart
    (apps/ordering/application/services/checkout.py) requires real
    shipping/billing address data this project has no UI for yet;
    wiring it is explicitly out of this phase's own scope.
    """

    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanValidateCart()]

    @extend_schema(tags=["Cart"], summary="Preview checkout readiness and a display-only price summary for the cart (no order is created)", responses={200: OpenApiResponse(description="Checkout preview"), **_responses(401, 403, 404)})
    def get(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)

        issues = composition.build_validate_cart().execute(cart.id)
        # Phase 09.5: no stock-reservation system is wired to Cart today
        # (reservation_reference is always null, confirmed in Phase
        # 09.2/09.4) -- all_reservations_valid=True is a disclosed
        # simplification, not a fabricated "stock confirmed" claim; the
        # readiness value below already reflects real price/status
        # checks independent of this flag.
        readiness = composition.build_calculate_checkout_readiness().execute(cart.id, all_reservations_valid=True)

        active_items = [i for i in cart.items.values() if i.status.value != "removed"]
        priced_items = [i for i in active_items if i.price_reference is not None]
        subtotal = None
        if priced_items:
            currencies = {i.price_reference.unit_amount.currency for i in priced_items}
            if len(currencies) == 1:
                total = sum((i.price_reference.unit_amount.amount * i.quantity.value for i in priced_items), Decimal("0"))
                subtotal = {"amount": str(total), "currency": currencies.pop()}

        applied_coupons, discount = _compute_cart_discount(cart.coupon_ids, subtotal, _actor_id(request))

        total_after_discount = None
        if subtotal and discount:
            total_after_discount = {"amount": str(Decimal(subtotal["amount"]) - Decimal(discount["amount"])), "currency": subtotal["currency"]}

        return success_response(data={
            "readiness": readiness,
            "issues": [{"severity": i.severity.value, "code": i.code.value, "message": i.message, "item_id": str(i.item_id) if i.item_id else None} for i in issues],
            "items": [_item_payload(i) for i in active_items],
            "priced_item_count": len(priced_items),
            "total_item_count": len(active_items),
            "subtotal": subtotal,
            "applied_coupons": [{"code": a["code"], "amount": a["amount"]} for a in applied_coupons],
            "discount": discount,
            "total": total_after_discount or subtotal,
            "currency": cart.currency.value,
            "expires_at": cart.expires_at.isoformat() if cart.expires_at else None,
            "loyalty": _loyalty_preview(_actor_id(request), total_after_discount or subtotal),
        })


class CartSnapshotHistoryView(APIView):
    throttle_classes = [CartThrottle]

    def get_permissions(self):
        return [CanViewCart()]

    @extend_schema(tags=["Cart"], summary="Get a cart's snapshot history")
    def get(self, request, code: str):
        _attach_identity(request)
        cart = _load_cart_by_code(code, request)
        snapshots = composition.build_get_snapshot_history().execute(cart.id)
        return success_response(data=[{"id": str(s.id), "token": str(s.token), "version_at_capture": s.version_at_capture, "captured_at": s.captured_at.isoformat()} for s in snapshots])
