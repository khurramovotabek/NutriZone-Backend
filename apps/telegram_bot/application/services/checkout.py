"""
Telegram checkout -- Phase 15D.

Reuses the exact same real composition CheckoutCartView itself uses
(confirmed via direct reading of apps/cart/interfaces/api/v1/views.py):
CalculateCheckoutReadiness, geo.Address, CreateOrderFromCart,
ConsumePriceSnapshot, all inside one shared transaction.atomic()
block -- learning directly from Phase 09.7c's own confirmed bug where
separate inner-atomic services committed independently rather than
together.

Address: the latitude/longitude Telegram's native "Share Location"
sends is stored in Address's coordinate fields, with our own city /
region / district for the point (apps/geo geocoder), and line1 is
the street from OpenStreetMap (or the honest coordinates when that's unavailable), never an invented street.
If the customer shares (almost) the same spot again, the saved address is reused instead of
creating a new one every time.

Idempotency: a real, minimal TelegramCheckoutConfirmation row with a
DB-level unique constraint on cart_id enforces "one confirmation, one
order" -- the same "let a real PostgreSQL constraint decide the race"
discipline already used throughout this project's own idempotency
infrastructure, not a new, weaker mechanism.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction

from common.exceptions import ResourceNotFound


class CheckoutNotReady(Exception):
    pass


class NoDeliveryAddress(Exception):
    """Raised when checkout:confirm is reached with no real, saved delivery address on file -- the customer must share their location via checkout:start first."""
    pass


class OrderAlreadyCreatedForThisCart(Exception):
    def __init__(self, order_number: str):
        self.order_number = order_number
        super().__init__(f"Order {order_number} already exists for this cart.")


SAME_PLACE_KM = 0.1  # a location shared within 100 m of the last saved point reuses that address


def get_or_create_default_address(user, latitude: float, longitude: float):
    """
    The location the customer shared with Telegram's native "Share Location" button becomes their delivery address:

    * shared again at (almost) the same spot → the latest saved address is reused;
    * a new spot → a new address (checkout always delivers to the newest one -- previously a customer with any saved
      address could share a new location and the order still went to the old one);
    * the address reads like one: street and house from OpenStreetMap ("Amir Temur ko'chasi 15"), our own city /
      region / district for the point (apps/geo/infrastructure/gateways/geocoder.py::locate). When the street service
      is unavailable the line is an honest "📍 41.31108, 69.24056" -- never an invented street.
    """
    from apps.geo.domain.services import AddressNormalizer
    from apps.geo.infrastructure import models as geo_orm
    from apps.geo.infrastructure.gateways import geocoder

    existing = geo_orm.Address.objects.filter(owner_type="user", owner_id=user.id).order_by("-created_at").first()
    if existing is not None and existing.coordinate_latitude is not None and \
            geocoder.haversine_km(existing.coordinate_latitude, existing.coordinate_longitude, latitude, longitude) <= SAME_PLACE_KM:
        return existing

    lang = getattr(user, "language", None) or "uz"
    try:
        found = geocoder.locate(latitude, longitude, lang if lang in geocoder.LANGS else "uz")
    except Exception:  # noqa: BLE001 - the address is saved even when lookup fails
        found = {}
    city = geo_orm.City.objects.filter(pk=(found.get("city") or {}).get("id")).select_related("region__country").first() if found.get("in_service_area") else None
    if city is None:  # outside the cities we know (or no reference data yet): Tashkent, as before
        country, _ = geo_orm.Country.objects.get_or_create(code="UZ", defaults={"status": "active"})
        region, _ = geo_orm.Region.objects.get_or_create(country=country, code="TGCITYR", defaults={"status": "active"})
        city, _ = geo_orm.City.objects.get_or_create(region=region, code="TGCITY1", defaults={"status": "active"})
        geo_orm.CityTranslation.objects.get_or_create(city=city, locale_code="en", defaults={"name": "Tashkent", "slug": "tashkent-telegram"})
    district_id = (found.get("district") or {}).get("id") if found.get("in_service_area") else None
    line1 = (found.get("street") or "").strip() or f"📍 {latitude:.5f}, {longitude:.5f}"
    label = (found.get("label") or "").strip()

    return geo_orm.Address.objects.create(
        id=uuid.uuid4(), owner_type="user", owner_id=user.id, address_type="residential",
        country=city.region.country, region=city.region, district_id=district_id, city=city, line1=line1[:255],
        formatted_single_line=label[:1024] or None,
        coordinate_latitude=latitude, coordinate_longitude=longitude, coordinate_source="telegram_native_share",
        normalized_signature=AddressNormalizer.normalized_signature(line1, None, str(city.id), None),
        # the bot knows the customer's name / phone from onboarding -- the address record is complete on its own
        recipient_name=user.full_name, recipient_phone=user.phone_number,
    )


def get_checkout_summary(user) -> dict:
    from apps.cart.infrastructure import composition as cart_composition

    if not user.telegram_cart_id:
        raise ResourceNotFound("Cart not found.")
    cart = cart_composition.build_cart_repository().get_by_id(user.telegram_cart_id)
    if cart is None:
        raise ResourceNotFound("Cart not found.")

    readiness = cart_composition.build_calculate_checkout_readiness().execute(cart.id, all_reservations_valid=True)

    active_items = [i for i in cart.items.values() if i.status.value != "removed"]
    total = Decimal("0")
    currency = cart.currency.value
    for item in active_items:
        if item.price_reference is not None:
            total += item.price_reference.unit_amount.amount * item.quantity.value

    return {"cart": cart, "readiness": readiness, "total": str(total), "currency": currency, "item_count": len(active_items)}


def confirm_cash_order(user) -> dict:
    from apps.cart.infrastructure import composition as cart_composition
    from apps.geo.infrastructure import models as geo_orm
    from apps.geo.infrastructure.repositories import DjangoCityRepository, DjangoCountryRepository
    from apps.identity.infrastructure.repositories import DjangoUserRepository
    from apps.ordering.infrastructure import composition as ordering_composition
    from apps.pricing.infrastructure import composition as pricing_composition
    from apps.telegram_bot.infrastructure import models as telegram_orm

    if not user.telegram_cart_id:
        raise ResourceNotFound("Cart not found.")
    cart = cart_composition.build_cart_repository().get_by_id(user.telegram_cart_id)
    if cart is None:
        raise ResourceNotFound("Cart not found.")

    readiness = cart_composition.build_calculate_checkout_readiness().execute(cart.id, all_reservations_valid=True)
    if readiness != "ready":
        raise CheckoutNotReady(f"Cart is not ready for checkout (status: {readiness}).")

    address = geo_orm.Address.objects.filter(owner_type="user", owner_id=user.id).order_by("-created_at").first()
    if address is None:
        raise NoDeliveryAddress("No real delivery address on file -- the customer must share their location via checkout:start before confirming.")

    active_items = [i for i in cart.items.values() if i.status.value != "removed"]
    if any(i.price_reference is None for i in active_items):
        raise CheckoutNotReady("Every item must have a confirmed price before checkout.")

    def _address_snapshot(addr):
        country = DjangoCountryRepository().get_by_id(addr.country_id)
        city = DjangoCityRepository().get_by_id(addr.city_id)
        u = DjangoUserRepository().get_by_id(user.id)
        # Real, product-required precedence: the address's own
        # recipient_name/recipient_phone (collected at checkout) take
        # priority -- see Cart API's own identical fix for the full
        # rationale. Falls back to the customer's own profile only
        # for an older address saved before this capability existed.
        recipient_name = addr.recipient_name or ((u.full_name or u.phone_number.value) if u else "")
        recipient_phone = addr.recipient_phone or (u.phone_number.value if u else None)
        return {
            "recipient_name": recipient_name,
            "phone": recipient_phone,
            "line1": addr.line1, "line2": addr.line2,
            "city": city.name if city else str(addr.city_id),
            "country_code": country.code.value if country else "",
            "postal_code": addr.postal_code.value if addr.postal_code else None,
            "latitude": addr.coordinate_latitude,
            "longitude": addr.coordinate_longitude,
        }

    line_items = [
        {"product_variant_id": str(item.product_variant_id), "quantity": item.quantity.value, "unit_price": str(item.price_reference.unit_amount.amount), "price_snapshot_id": str(item.price_reference.price_snapshot_id)}
        for item in active_items
    ]

    try:
        with transaction.atomic():
            telegram_orm.TelegramCheckoutConfirmation.objects.create(id=uuid.uuid4(), cart_id=cart.id, customer_id=user.id)

            order = ordering_composition.build_create_order_from_cart(user.id).execute(
                cart_id=cart.id, customer_id=user.id, currency=cart.currency.value,
                shipping_address=_address_snapshot(address), billing_address=_address_snapshot(address),
                line_items=line_items, coupon_ids=[uuid.UUID(c) for c in cart.coupon_ids],
            )
            consume_snapshot = pricing_composition.build_consume_price_snapshot(user.id)
            for item in active_items:
                consume_snapshot.execute(item.price_reference.price_snapshot_id)
    except IntegrityError:
        existing_confirmation = telegram_orm.TelegramCheckoutConfirmation.objects.filter(cart_id=cart.id).first()
        if existing_confirmation and existing_confirmation.order_number:
            raise OrderAlreadyCreatedForThisCart(existing_confirmation.order_number)
        raise

    telegram_orm.TelegramCheckoutConfirmation.objects.filter(cart_id=cart.id).update(order_number=order.order_number.value)

    total = sum((Decimal(li["unit_price"]) * li["quantity"] for li in line_items), Decimal("0"))
    return {"order_number": order.order_number.value, "total": str(total), "currency": cart.currency.value}
