"""
Guest checkout: order without signing in -- a name, a phone typed in any shape and a delivery point (or a branch).

  GET  /carts/<code>/guest-preview   prices the guest cart server-side (same price snapshots a signed-in cart gets) and
                                     quotes delivery for a place that isn't saved yet (?city_id/region_id + lat/lng)
  POST /carts/<code>/guest-checkout  resolves the customer by phone (identity/guests.py), saves the address on that
                                     account and places the order through the very same place_order() a signed-in
                                     checkout uses; an online method returns the provider's page URL.

Only a cart with no owner, proven by its X-Cart-Token, can be used. A phone that already has an account gets the order
on that account but never a session; a brand-new number gets a guest account and its session (so the order page,
online payment and the next order just work). Guests earn no coins -- signing up does.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.cart.infrastructure import composition
from common.exceptions import ConflictError, ValidationFailed
from common.exceptions import PermissionDenied as DomainPermissionDenied
from common.responses import success_response
from core.ratelimit import ScopedRateLimitThrottle

from .views import _load_cart_by_code, place_order, preview_payload


class GuestPreviewThrottle(ScopedRateLimitThrottle):
    scope = "cart.guest_preview"
    limit = 600
    window_seconds = 3600
    identifier_source = "ip"


class GuestCheckoutThrottle(ScopedRateLimitThrottle):
    scope = "cart.guest_checkout"
    limit = 20
    window_seconds = 3600
    identifier_source = "ip"


class GuestAddressSerializer(serializers.Serializer):
    country_id = serializers.UUIDField()
    city_id = serializers.UUIDField()
    region_id = serializers.UUIDField(required=False, allow_null=True)
    district_id = serializers.UUIDField(required=False, allow_null=True)
    line1 = serializers.CharField(max_length=255)
    metadata = serializers.DictField(child=serializers.CharField(allow_blank=True, max_length=500), required=False)
    latitude = serializers.FloatField(required=False, allow_null=True, min_value=-90, max_value=90)
    longitude = serializers.FloatField(required=False, allow_null=True, min_value=-180, max_value=180)
    source = serializers.CharField(required=False, allow_blank=True, max_length=32)
    accuracy_meters = serializers.FloatField(required=False, allow_null=True, min_value=0, max_value=100000)


class GuestCheckoutSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=40)
    fulfilment_method = serializers.ChoiceField(choices=("delivery", "pickup"), default="delivery")
    pickup_store_id = serializers.UUIDField(required=False)
    address = GuestAddressSerializer(required=False)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=500)
    payment_method = serializers.CharField(required=False, allow_blank=True, max_length=20)
    language = serializers.CharField(required=False, allow_blank=True, max_length=5)
    return_url = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate(self, attrs):
        if attrs["fulfilment_method"] == "pickup" and not attrs.get("pickup_store_id"):
            raise serializers.ValidationError({"pickup_store_id": "Choose the store to pick up from."})
        if attrs["fulfilment_method"] == "delivery" and not attrs.get("address"):
            raise serializers.ValidationError({"address": "A delivery address is required."})
        return attrs


def _guest_cart(code: str, request):
    cart = _load_cart_by_code(code, request)
    if cart.customer_id is not None:  # a signed-in customer's cart goes through the normal checkout
        raise DomainPermissionDenied("This cart belongs to an account -- sign in to check out.")
    return cart


def _price_unpriced(cart) -> object:
    """Locks today's price on every unpriced (or expired) line -- server-side, never a client price."""
    from apps.pricing.infrastructure import composition as pricing_composition

    changed = False
    for item in [i for i in cart.items.values() if i.status.value != "removed" and i.price_reference is None]:
        try:
            snap = pricing_composition.build_issue_variant_price_snapshot(None).execute(
                product_variant_id=item.product_variant_id, quantity=item.quantity.value, region=cart.region.value if cart.region else None)
            composition.build_attach_price_snapshot(None).execute(cart_id=cart.id, item_id=item.id, price_snapshot_id=snap.id,
                                                                  unit_amount=snap.locked_price.amount, currency=snap.locked_price.currency)
            changed = True
        except Exception:  # noqa: BLE001 - a line without an active price shows as an issue in the preview
            continue
    return composition.build_load_cart().execute(code=cart.code.value) if changed else cart


def _reprice_all(cart):
    """Re-locks every line (their locks expired while the cart sat open) -- used once if checkout says so."""
    from apps.pricing.infrastructure import composition as pricing_composition

    for item in [i for i in cart.items.values() if i.status.value != "removed"]:
        snap = pricing_composition.build_issue_variant_price_snapshot(None).execute(
            product_variant_id=item.product_variant_id, quantity=item.quantity.value, region=cart.region.value if cart.region else None)
        composition.build_attach_price_snapshot(None).execute(cart_id=cart.id, item_id=item.id, price_snapshot_id=snap.id,
                                                              unit_amount=snap.locked_price.amount, currency=snap.locked_price.currency)
    return composition.build_load_cart().execute(code=cart.code.value)


def _uuid(raw):
    try:
        return uuid.UUID(str(raw)) if raw else None
    except ValueError:
        return None


def _float(raw):
    try:
        return float(raw) if raw not in (None, "") else None
    except ValueError:
        return None


def _quote_line(q) -> dict | None:
    if q is None:
        return None
    return {"method": "delivery", "zone": q.zone, "carrier": q.carrier, "fee": str(q.fee), "base_fee": str(q.base_fee), "eta": q.eta,
            "free_from": str(q.free_from) if q.free_from is not None else None, "weight_kg": q.weight_kg, "distance_km": q.distance_km}


class GuestCheckoutPreviewView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [GuestPreviewThrottle]

    def get(self, request, code: str):
        from apps.ordering.infrastructure import delivery_pricing

        cart = _price_unpriced(_guest_cart(code, request))
        p = request.query_params
        lang = (p.get("lang") or "uz")[:2]

        def delivery(total, items):
            if total is None:
                return None
            if p.get("method") == "pickup":
                return {"method": "pickup", "zone": None, "carrier": "", "fee": "0", "base_fee": "0", "eta": "", "free_from": None}
            city, region = _uuid(p.get("city_id")), _uuid(p.get("region_id"))
            if not city and not region:
                return None
            return _quote_line(delivery_pricing.quote_for_point(city, _float(p.get("lat")), _float(p.get("lng")), Decimal(total["amount"]), lang, items=items, region_id=region))

        return success_response(data=preview_payload(cart, None, delivery))


def _save_address(user, data: dict, full_name: str, phone: str):
    """The guest's delivery place as an address of their account (an identical one already there is reused)."""
    from apps.geo.domain.services import AddressNormalizer
    from apps.geo.domain.exceptions import DuplicateAddressDetected
    from apps.geo.infrastructure import composition as geo_composition
    from apps.geo.infrastructure.models import Address

    metadata = {k: v.strip() for k, v in (data.get("metadata") or {}).items() if k in ("building_name", "entrance", "floor", "unit", "entrance_code", "delivery_instructions") and v and v.strip()}
    try:
        address = geo_composition.build_create_address(user.id).execute(
            owner_type="user", owner_id=user.id, address_type="residential", country_id=data["country_id"], city_id=data["city_id"],
            region_id=data.get("region_id"), district_id=data.get("district_id"), line1=data["line1"].strip(),
            recipient_name=full_name, recipient_phone=phone, metadata=metadata or None)
        address_id = address.id
    except DuplicateAddressDetected:
        signature = AddressNormalizer.normalized_signature(data["line1"].strip(), None, str(data["city_id"]), None)
        row = Address.objects.filter(owner_type="user", owner_id=user.id, normalized_signature=signature).first()
        if row is None:
            raise
        Address.objects.filter(pk=row.pk).update(recipient_name=full_name, recipient_phone=phone, **({"metadata": {**(row.metadata or {}), **metadata}} if metadata else {}))
        address_id = row.id
    if data.get("latitude") is not None and data.get("longitude") is not None:
        geo_composition.build_assign_coordinates(user.id).execute(
            address_id=address_id, latitude=data["latitude"], longitude=data["longitude"], source=data.get("source") or "map_pin", accuracy_meters=data.get("accuracy_meters"))
    return address_id


class GuestCheckoutView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [GuestCheckoutThrottle]

    def post(self, request, code: str):
        from apps.identity.infrastructure import guests

        cart = _price_unpriced(_guest_cart(code, request))
        s = GuestCheckoutSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        lang = (d.get("language") or "uz")[:2]
        try:
            user, created = guests.find_or_create(d["phone"], d["full_name"], lang)
        except guests.GuestError as exc:
            err = ValidationFailed(exc.message, details={"fields": [{"field": "phone" if "PHONE" in exc.code else "full_name", "code": exc.code}]})
            if exc.code == "ACCOUNT_BLOCKED":
                err = ConflictError(exc.message)
                err.code = exc.code
            raise err from exc
        full_name = " ".join(d["full_name"].split())
        with transaction.atomic():
            address_id = _save_address(user, d["address"], full_name, user.phone_number) if d["fulfilment_method"] == "delivery" else None
        if d.get("comment", "").strip():
            from apps.cart.infrastructure.models import CartModel

            CartModel.objects.filter(pk=cart.id).update(note=d["comment"].strip()[:500])
            cart = composition.build_load_cart().execute(code=cart.code.value)

        request.user = user  # place_order reads the language / actor from the request like a signed-in checkout
        data = {"fulfilment_method": d["fulfilment_method"], "pickup_store_id": d.get("pickup_store_id"), "shipping_address_id": address_id, "coins_to_redeem": 0}
        try:
            response = place_order(request, cart, user.id, data)
        except Exception as exc:  # noqa: BLE001
            if getattr(exc, "code", "") != "PRICE_SNAPSHOT_EXPIRED":
                raise
            response = place_order(request, _reprice_all(cart), user.id, data)

        payload = response.data.get("data") or {}
        payload["account"] = "new" if created else ("guest" if user.is_guest else "existing")
        if created:
            try:
                payload["session"] = guests.issue_session(user, request)
            except Exception:  # noqa: BLE001 - the order is placed; the customer can still sign in later
                import logging

                logging.getLogger("nutrizone.app").exception("guest checkout: could not issue a session for %s", user.id)
        method = (d.get("payment_method") or "").strip()
        if method and method != "cash" and response.status_code in (200, 201):
            from apps.payment.infrastructure import service as payments

            try:
                started = payments.start_payment(user.id, payload["order_number"], method, lang, return_to=d.get("return_url") or None)
                payload["checkout_url"] = started.checkout_url
            except Exception:  # noqa: BLE001 - the order stands; the customer can pay from the order page / on delivery
                payload["checkout_url"] = None
        response.data["data"] = payload
        return response
