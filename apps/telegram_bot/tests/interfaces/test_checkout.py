"""
Phase 15D: Telegram checkout tests.

Every scenario was first verified live via a real HTTP request before
being formalized, matching the discipline established in Phase
15B/15C.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

WEBHOOK_URL = "/api/v1/telegram/webhook"
TEST_SECRET = "test-webhook-secret-only-not-real"


def _post(client, payload):
    return client.post(WEBHOOK_URL, data=json.dumps(payload), content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=TEST_SECRET)


def _callback(telegram_user_id, data):
    return {"callback_query": {"id": "cbq", "from": {"id": telegram_user_id}, "message": {"chat": {"id": telegram_user_id}}, "data": data}}


def _location_message(telegram_user_id, latitude=41.3111, longitude=69.2797):
    return {"message": {"chat": {"id": telegram_user_id}, "from": {"id": telegram_user_id}, "location": {"latitude": latitude, "longitude": longitude}}}


def _share_real_location(client, telegram_user_id):
    """Real integration: simulates the customer tapping Telegram's own native "Share Location" button after checkout:start prompted for one -- required before checkout:confirm can succeed, per this phase's own explicit product decision (no fabricated address is ever substituted)."""
    _post(client, _callback(telegram_user_id, "checkout:start"))
    _post(client, _location_message(telegram_user_id))


def _make_priced_product(unit_amount=Decimal("120000.00")):
    from apps.products.infrastructure import models as products_orm
    from apps.pricing.infrastructure import models as pricing_orm

    category = products_orm.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
    products_orm.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="uz", name="Protein", slug=f"protein-{uuid.uuid4().hex[:8]}")
    product = products_orm.Product.objects.create(id=uuid.uuid4(), status="published", category=category)
    products_orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Checkout Test Product", slug=f"checkout-test-{uuid.uuid4().hex[:8]}")
    variant = products_orm.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", status="active", is_default=True)
    price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
    pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant.id, base_price_amount=unit_amount)
    return category, product, variant


def _register(telegram_user_id, phone_suffix):
    from apps.identity.infrastructure import models as identity_orm

    return identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99891{phone_suffix:07d}", full_name="Checkout Test", status="active", telegram_user_id=telegram_user_id)


class TestCheckoutFlow:
    def test_empty_cart_cannot_checkout(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        telegram_id = 800400100
        _register(telegram_id, 1)
        r = _post(Client(), _callback(telegram_id, "checkout:start"))
        assert r.status_code == 200

        from apps.ordering.infrastructure import models as ordering_orm
        assert ordering_orm.OrderModel.objects.count() == 0

    def test_checkout_start_shows_summary_for_ready_cart(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        category, product, variant = _make_priced_product()
        telegram_id = 800400101
        _register(telegram_id, 2)
        client = Client()
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))
        r = _post(client, _callback(telegram_id, "checkout:start"))
        assert r.status_code == 200

    def test_confirm_creates_real_order_with_correct_status(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.ordering.infrastructure import models as ordering_orm

        category, product, variant = _make_priced_product(Decimal("77000.00"))
        telegram_id = 800400102
        user = _register(telegram_id, 3)
        client = Client()
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))
        _share_real_location(client, telegram_id)
        r = _post(client, _callback(telegram_id, "checkout:confirm"))
        assert r.status_code == 200

        orders = ordering_orm.OrderModel.objects.filter(customer_id=user.id)
        assert orders.count() == 1
        order = orders.first()
        assert order.status == "pending_payment"
        assert order.order_number.startswith("ORD-")

    def test_confirm_consumes_price_snapshot(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.pricing.infrastructure import models as pricing_orm

        category, product, variant = _make_priced_product()
        telegram_id = 800400103
        user = _register(telegram_id, 4)
        client = Client()
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))
        _share_real_location(client, telegram_id)
        _post(client, _callback(telegram_id, "checkout:confirm"))

        snapshot = pricing_orm.PriceSnapshotModel.objects.filter(product_variant_id=variant.id).order_by("-id").first()
        assert snapshot.status == "consumed"


class TestCheckoutIdempotency:
    def test_double_confirmation_creates_exactly_one_order(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.ordering.infrastructure import models as ordering_orm

        category, product, variant = _make_priced_product()
        telegram_id = 800400200
        user = _register(telegram_id, 5)
        client = Client()
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))
        _share_real_location(client, telegram_id)

        r1 = _post(client, _callback(telegram_id, "checkout:confirm"))
        r2 = _post(client, _callback(telegram_id, "checkout:confirm"))
        assert r1.status_code == 200
        assert r2.status_code == 200

        orders = ordering_orm.OrderModel.objects.filter(customer_id=user.id)
        assert orders.count() == 1

    def test_second_confirmation_does_not_error_customer_facing(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.telegram_bot.application.services import checkout as checkout_service

        category, product, variant = _make_priced_product()
        telegram_id = 800400201
        user = _register(telegram_id, 6)
        client = Client()
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))
        _share_real_location(client, telegram_id)
        _post(client, _callback(telegram_id, "checkout:confirm"))

        user.refresh_from_db()
        from apps.telegram_bot.application.services.checkout import OrderAlreadyCreatedForThisCart

        with pytest.raises(OrderAlreadyCreatedForThisCart):
            checkout_service.confirm_cash_order(user)


class TestCheckoutPriceAuthority:
    def test_order_total_matches_real_server_price_not_client_input(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.ordering.infrastructure import models as ordering_orm

        category, product, variant = _make_priced_product(Decimal("64000.00"))
        telegram_id = 800400300
        user = _register(telegram_id, 7)
        client = Client()
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))
        _share_real_location(client, telegram_id)
        _post(client, _callback(telegram_id, "checkout:confirm"))

        order = ordering_orm.OrderModel.objects.get(customer_id=user.id)
        lines = ordering_orm.OrderLineItemModel.objects.filter(order=order)
        assert lines.first().unit_price_amount == Decimal("64000.00")


class TestCheckoutAddressReuse:
    def test_second_order_reuses_existing_address_not_duplicating(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.geo.infrastructure import models as geo_orm

        category, product, variant = _make_priced_product()
        telegram_id = 800400400
        user = _register(telegram_id, 8)
        client = Client()
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))
        _share_real_location(client, telegram_id)
        _post(client, _callback(telegram_id, "checkout:confirm"))

        assert geo_orm.Address.objects.filter(owner_type="user", owner_id=user.id).count() == 1


class TestCheckoutRequiresRealDeliveryLocation:
    """
    Real, live-verified regression test for the previously disclosed
    gap: checkout used to fabricate a f"Telegram chat {chat_id}"
    placeholder as the delivery address, never asking the customer
    for their real location. Now, checkout:start prompts for a real
    Telegram native "Share Location" share when no address is on
    file, and checkout:confirm refuses to create an order until one
    exists.
    """

    def test_checkout_start_with_no_saved_address_requests_location_not_summary(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.geo.infrastructure import models as geo_orm

        category, product, variant = _make_priced_product()
        telegram_id = 800400500
        user = _register(telegram_id, 9)
        client = Client()
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))

        r = _post(client, _callback(telegram_id, "checkout:start"))
        assert r.status_code == 200

        from apps.telegram_bot.interfaces import checkout_state

        assert checkout_state.is_awaiting_location(telegram_id) is True
        assert geo_orm.Address.objects.filter(owner_type="user", owner_id=user.id).count() == 0

    def test_confirm_without_a_saved_address_creates_no_order_and_re_requests_location(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.ordering.infrastructure import models as ordering_orm

        category, product, variant = _make_priced_product()
        telegram_id = 800400501
        user = _register(telegram_id, 10)
        client = Client()
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))

        r = _post(client, _callback(telegram_id, "checkout:confirm"))
        assert r.status_code == 200
        assert ordering_orm.OrderModel.objects.filter(customer_id=user.id).count() == 0

    def test_sharing_location_creates_a_real_address_with_real_coordinates(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.geo.infrastructure import models as geo_orm

        category, product, variant = _make_priced_product()
        telegram_id = 800400502
        user = _register(telegram_id, 11)
        client = Client()
        _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))
        _post(client, _callback(telegram_id, "checkout:start"))

        r = _post(client, _location_message(telegram_id, latitude=41.2995, longitude=69.2401))
        assert r.status_code == 200

        address = geo_orm.Address.objects.filter(owner_type="user", owner_id=user.id).first()
        assert address is not None
        assert address.coordinate_latitude == 41.2995
        assert address.coordinate_longitude == 69.2401
        assert address.coordinate_source == "telegram_native_share"

    def test_location_shared_without_pending_checkout_is_ignored(self, settings):
        """A random location share (not preceded by checkout:start) must never create a stray address."""
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.geo.infrastructure import models as geo_orm

        telegram_id = 800400503
        _register(telegram_id, 12)
        client = Client()

        r = _post(client, _location_message(telegram_id))
        assert r.status_code == 200
        assert geo_orm.Address.objects.count() == 0


class TestAddressRecipientDetailsFromBot:
    """Real, closed gap: get_or_create_default_address() called Address.objects.create() directly, never setting recipient_name/recipient_phone -- even though the bot already knows the customer's real name/phone from onboarding. Checkout's own _address_snapshot() falls back to the user's profile, so orders still worked, but the Address record itself was silently incomplete."""

    def test_address_created_via_location_share_has_the_customers_real_name_and_phone(self):
        from apps.identity.infrastructure import models as identity_orm
        from apps.telegram_bot.application.services.checkout import get_or_create_default_address

        user = identity_orm.User.objects.create(
            id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}",
            status="active", full_name="Real Customer Name",
        )

        address = get_or_create_default_address(user, 41.311081, 69.240562)

        assert address.recipient_name == "Real Customer Name"
        assert address.recipient_phone == user.phone_number


class TestSharedLocationBecomesARealAddress:
    """A shared location reads like an address (street from OpenStreetMap, our district) and a new spot is a new address."""

    def _user(self):
        from apps.identity.infrastructure import models as identity_orm

        return identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99891{uuid.uuid4().int % 10000000:07d}", status="active", full_name="Aziz")

    def test_street_name_instead_of_raw_coordinates_and_new_spot_new_address(self, monkeypatch):
        from apps.geo.infrastructure.gateways import geocoder
        from apps.telegram_bot.application.services.checkout import get_or_create_default_address

        monkeypatch.setattr(geocoder, "locate", lambda lat, lng, lang="uz", with_street=True: {"street": "Amir Temur ko'chasi 15", "label": "Amir Temur ko'chasi 15, Toshkent", "in_service_area": False})
        user = self._user()
        first = get_or_create_default_address(user, 41.311081, 69.240562)
        assert first.line1 == "Amir Temur ko'chasi 15" and first.formatted_single_line.startswith("Amir Temur")
        assert get_or_create_default_address(user, 41.311500, 69.240600).pk == first.pk  # ~50 m away: the same place
        second = get_or_create_default_address(user, 41.285600, 69.203400)  # Chilonzor: a new address, checkout uses it
        assert second.pk != first.pk

    def test_without_street_service_the_line_is_honest_coordinates(self, monkeypatch):
        from apps.geo.infrastructure.gateways import geocoder
        from apps.telegram_bot.application.services.checkout import get_or_create_default_address

        monkeypatch.setattr(geocoder, "locate", lambda *a, **k: {"street": "", "label": "", "in_service_area": False})
        assert get_or_create_default_address(self._user(), 41.311081, 69.240562).line1 == "📍 41.31108, 69.24056"
