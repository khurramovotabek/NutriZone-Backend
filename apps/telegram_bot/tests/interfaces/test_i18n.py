"""
Phase 15G: Telegram bot i18n tests.

Every scenario was first verified live via real HTTP requests before
being formalized, matching the discipline established throughout
Phase 15B-15F.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

WEBHOOK_URL = "/api/v1/telegram/webhook"
TEST_SECRET = "test-webhook-secret-only-not-real"


class _FakeGateway:
    def __init__(self):
        self.text_messages = []
        self.keyboard_messages = []

    def send_message(self, chat_id, title, body):
        self.text_messages.append(body)
        return "fake-id"

    def send_message_with_keyboard(self, chat_id, text, keyboard):
        self.text_messages.append(text)
        self.keyboard_messages.append(keyboard)
        return "fake-id"

    def send_location_request(self, chat_id, text, button_text):
        self.text_messages.append(text)
        return "fake-id"

    def edit_message_text(self, chat_id, message_id, text, inline_keyboard=None):
        pass


def _post(client, payload):
    return client.post(WEBHOOK_URL, data=json.dumps(payload), content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=TEST_SECRET)


def _callback(telegram_user_id, data):
    return {"callback_query": {"id": "cbq", "from": {"id": telegram_user_id}, "message": {"chat": {"id": telegram_user_id}, "message_id": "1"}, "data": data}}


def _register(telegram_user_id, phone_suffix):
    from apps.identity.infrastructure import models as identity_orm

    return identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99893{phone_suffix:07d}", full_name="i18n Test", status="active", telegram_user_id=telegram_user_id)


class TestTranslationLookup:
    def test_known_key_returns_correct_language(self):
        from apps.telegram_bot.interfaces.i18n import t

        assert "Katalog" in t("menu_catalog", "uz")
        assert "Каталог" in t("menu_catalog", "ru")
        assert "Catalog" in t("menu_catalog", "en")

    def test_formatting_kwargs_are_applied(self):
        from apps.telegram_bot.interfaces.i18n import t

        result = t("cart_total", "en", total="1000", currency="UZS")
        assert "1000" in result and "UZS" in result

    def test_unknown_language_falls_back_to_english(self):
        from apps.telegram_bot.interfaces.i18n import t

        assert t("menu_catalog", "fr") == t("menu_catalog", "en")

    def test_unknown_key_never_raises(self):
        from apps.telegram_bot.interfaces.i18n import t

        assert t("this_key_does_not_exist", "en") == "this_key_does_not_exist"


class TestNewCustomerDefaultLanguage:
    def test_new_telegram_registration_defaults_to_uzbek(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.identity.infrastructure import models as identity_orm

        telegram_id = 800800100
        update = {"message": {"message_id": 1, "from": {"id": telegram_id, "first_name": "Test"}, "chat": {"id": telegram_id}, "contact": {"phone_number": "998930001100", "user_id": telegram_id}}}
        _post(Client(), update)

        user = identity_orm.User.objects.get(telegram_user_id=telegram_id)
        assert user.language == "uz"


class TestLanguageSwitching:
    def test_switching_language_persists_to_user(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.notifications.infrastructure import composition as notifications_composition

        telegram_id = 800800200
        user = _register(telegram_id, 1)
        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_telegram_gateway", return_value=fake_gateway):
            _post(Client(), _callback(telegram_id, "menu:setlang:ru"))

        user.refresh_from_db()
        assert user.language == "ru"

    def test_invalid_language_code_is_ignored(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.notifications.infrastructure import composition as notifications_composition

        telegram_id = 800800201
        user = _register(telegram_id, 2)
        original_language = user.language
        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_telegram_gateway", return_value=fake_gateway):
            r = _post(Client(), _callback(telegram_id, "menu:setlang:xx"))
        assert r.status_code == 200

        user.refresh_from_db()
        assert user.language == original_language

    def test_catalog_message_reflects_chosen_language(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.notifications.infrastructure import composition as notifications_composition

        telegram_id = 800800300
        user = _register(telegram_id, 3)
        user.language = "ru"
        user.save(update_fields=["language"])

        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_telegram_gateway", return_value=fake_gateway):
            _post(Client(), _callback(telegram_id, "menu:catalog"))

        assert any("Категории пока недоступны" in msg for msg in fake_gateway.text_messages)

    def test_cart_message_reflects_english(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.notifications.infrastructure import composition as notifications_composition

        telegram_id = 800800301
        user = _register(telegram_id, 4)
        user.language = "en"
        user.save(update_fields=["language"])

        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_telegram_gateway", return_value=fake_gateway):
            _post(Client(), _callback(telegram_id, "menu:cart"))

        assert any("Your cart is currently empty" in msg for msg in fake_gateway.text_messages)

    def test_main_menu_buttons_reflect_chosen_language(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.notifications.infrastructure import composition as notifications_composition

        telegram_id = 800800302
        user = _register(telegram_id, 5)
        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_telegram_gateway", return_value=fake_gateway):
            _post(Client(), _callback(telegram_id, "menu:setlang:ru"))

        last_keyboard = fake_gateway.keyboard_messages[-1]
        button_texts = [btn["text"] for row in last_keyboard for btn in row]
        assert any("Каталог" in text for text in button_texts)


class TestEndToEndLocalizedCheckout:
    def test_full_shopping_flow_in_russian(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.notifications.infrastructure import composition as notifications_composition
        from apps.products.infrastructure import models as products_orm
        from apps.pricing.infrastructure import models as pricing_orm
        from apps.ordering.infrastructure import models as ordering_orm

        category = products_orm.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
        products_orm.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="uz", name="Protein", slug=f"protein-{uuid.uuid4().hex[:8]}")
        product = products_orm.Product.objects.create(id=uuid.uuid4(), status="published", category=category)
        products_orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="RU Flow Test", slug=f"ru-flow-{uuid.uuid4().hex[:8]}")
        variant = products_orm.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", status="active", is_default=True)
        price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
        pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant.id, base_price_amount=Decimal("40000.00"))

        telegram_id = 800800400
        user = _register(telegram_id, 6)
        user.language = "ru"
        user.save(update_fields=["language"])

        fake_gateway = _FakeGateway()
        client = Client()
        with patch.object(notifications_composition, "build_telegram_gateway", return_value=fake_gateway):
            _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))
            _post(client, _callback(telegram_id, "checkout:start"))
            _post(client, {"message": {"chat": {"id": telegram_id}, "from": {"id": telegram_id}, "location": {"latitude": 41.3111, "longitude": 69.2797}}})
            _post(client, _callback(telegram_id, "checkout:confirm"))

        order = ordering_orm.OrderModel.objects.get(customer_id=user.id)
        assert order.status == "pending_payment"
        assert any("заказ" in msg.lower() or "принят" in msg.lower() for msg in fake_gateway.text_messages)
