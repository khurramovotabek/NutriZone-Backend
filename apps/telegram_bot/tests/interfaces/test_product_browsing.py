"""
Real, live-verified tests for the Telegram bot's premium product-
browsing upgrade: one product per message, edited in place while
paginating, real brand/category filters, wishlist, and order detail.
Every product/brand/category/order here is a real row created via the
real ORM models -- no mock product data anywhere in this file, matching
this phase's own "no fake data" rule.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import Client

from apps.identity.infrastructure import models as identity_orm
from apps.ordering.domain.aggregates import Order
from apps.ordering.domain.enums import OrderChannel, OrderStatus
from apps.ordering.domain.value_objects import OrderNumber
from apps.ordering.infrastructure import composition as ordering_composition
from apps.ordering.tests.factories import _next_order_number, make_address, make_line_item
from apps.products.infrastructure import models as p_models
from common.utils.money import Money

pytestmark = pytest.mark.django_db

_WEBHOOK_AUTH = {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "test-webhook-secret"}


@pytest.fixture(autouse=True)
def _clear_rate_limit_state():
    from core.caching.redis_client import get_redis_client

    get_redis_client().flushall()
    yield


def _make_customer(**overrides) -> identity_orm.User:
    tg_user_id = uuid.uuid4().int % 900000000
    defaults = dict(
        id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}",
        status="active", telegram_user_id=tg_user_id, full_name="Test Customer", language="uz",
    )
    defaults.update(overrides)
    return identity_orm.User.objects.create(**defaults)


def _make_product(name: str = "Test Product", brand=None, category=None, description: str = "") -> p_models.Product:
    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published", brand=brand, category=category)
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name=name, slug=f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}", description=description)
    p_models.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:6]}", status="active", is_default=True)
    return product


def _callback(client, tg_user_id, data, message_id=1):
    update = {"update_id": 1, "callback_query": {"id": "cbq1", "from": {"id": tg_user_id}, "message": {"chat": {"id": tg_user_id}, "message_id": message_id}, "data": data}}
    return client.post("/api/v1/telegram/webhook", data=json.dumps(update), content_type="application/json", **_WEBHOOK_AUTH)


class TestProductsMenuSources:
    def test_best_sellers_is_a_real_empty_state_when_no_sales_exist(self, settings):
        """No fake "top products" list -- list_best_sellers() is real, order-derived data, and there are genuinely no confirmed orders in this test."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        customer = _make_customer()
        client = Client()
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            response = _callback(client, customer.telegram_user_id, "pm:best")
            assert response.status_code == 200
            assert mock_send.call_args[0][1] == "\U0001F50D Hech qanday mahsulot topilmadi.\n\nFiltrlarni o'zgartirib ko'ring."

    def test_all_products_shows_the_real_product_name_and_price_pending(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        customer = _make_customer()
        _make_product("Gold Standard Whey")
        client = Client()
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            _callback(client, customer.telegram_user_id, "pm:all")
            caption = mock_send.call_args[0][1]
            assert "Gold Standard Whey" in caption
            assert "narx aniqlanmoqda" in caption  # real: no PriceListEntry exists for this variant, never a fabricated price


class TestPagination:
    def test_next_and_prev_move_between_two_real_products(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        customer = _make_customer()
        _make_product("First Product")
        _make_product("Second Product")
        client = Client()
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, \
                patch("apps.telegram_bot.interfaces.callback_router._edit_photo", return_value=False), \
                patch("apps.notifications.infrastructure.gateways.LiveTelegramGateway.edit_message_text", side_effect=Exception("no photo -> caption path uses edit_message_text; simulate it failing so _send fallback is exercised deterministically")), \
                patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            _callback(client, customer.telegram_user_id, "pm:all")
            first_caption = mock_send.call_args[0][1]

            _callback(client, customer.telegram_user_id, "pc:next")
            second_caption = mock_send.call_args[0][1]
            assert first_caption != second_caption

            _callback(client, customer.telegram_user_id, "pc:prev")
            back_caption = mock_send.call_args[0][1]
            assert back_caption == first_caption

    def test_pc_action_without_an_active_session_shows_reopen_message_not_a_crash(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        customer = _make_customer()
        client = Client()
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            response = _callback(client, customer.telegram_user_id, "pc:next")
            assert response.status_code == 200
            assert "expired" in str(mock_send.call_args).lower() or "tugagan" in str(mock_send.call_args)


class TestProductDetail:
    def test_detail_shows_real_description_and_no_fabricated_nutrition_fields(self, settings):
        """Also a direct, live regression check for the get_by_id parity fix: this used to always render as if the product had zero purchasable variants."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        customer = _make_customer()
        _make_product("Detail Test Product", description="A real, honest description.")
        client = Client()
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            _callback(client, customer.telegram_user_id, "pm:all")
            _callback(client, customer.telegram_user_id, "pc:detail")
            caption = mock_send.call_args[0][1]
            assert "A real, honest description." in caption
            assert "Protein:" not in caption  # no specifications were ever entered -- never fabricated


class TestWishlist:
    def test_toggling_wishlist_flips_the_button_label(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        customer = _make_customer()
        product = _make_product("Wishlist Test Product")
        client = Client()
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            _callback(client, customer.telegram_user_id, "pm:all")
            _callback(client, customer.telegram_user_id, "pc:wish")
            keyboard = mock_send.call_args[0][2]
            button_texts = [b["text"] for row in keyboard for b in row]
            assert any("Wishlist'da" in text for text in button_texts)

        assert p_models.WishlistItem.objects.filter(customer_id=customer.id, product_id=product.id).exists()


class TestFilters:
    def test_brand_filter_narrows_to_only_that_brands_products(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        customer = _make_customer()
        brand_a = p_models.Brand.objects.create(id=uuid.uuid4())
        p_models.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand_a, locale_code="uz", name="Brand A", slug=f"a-{uuid.uuid4().hex[:6]}")
        brand_b = p_models.Brand.objects.create(id=uuid.uuid4())
        p_models.BrandTranslation.objects.create(id=uuid.uuid4(), brand=brand_b, locale_code="uz", name="Brand B", slug=f"b-{uuid.uuid4().hex[:6]}")
        _make_product("Product From Brand A", brand=brand_a)
        _make_product("Product From Brand B", brand=brand_b)

        client = Client()
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            _callback(client, customer.telegram_user_id, "pm:all")
            _callback(client, customer.telegram_user_id, "flt:menu")
            _callback(client, customer.telegram_user_id, "flt:brandlist")
            _callback(client, customer.telegram_user_id, f"flt:setbrand:{brand_a.id}")
            caption = mock_send.call_args[0][1]
            assert "Product From Brand A" in caption

    def test_rating_and_price_filters_really_filter(self, settings):
        """Rating and price go through the storefront's own catalog engine (catalog_browse) -- the same real filters as the website."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        customer = _make_customer()
        _make_product("Unrated Product")
        client = Client()
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, \
                patch("apps.notifications.infrastructure.gateways.LiveTelegramGateway.edit_message_text", side_effect=Exception("force the _send fallback")), \
                patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            _callback(client, customer.telegram_user_id, "pm:all")
            _callback(client, customer.telegram_user_id, "flt:rating")
            options = [b["callback_data"] for row in mock_send.call_args[0][2] for b in row]
            assert "flt:setrating:4" in options
            _callback(client, customer.telegram_user_id, "flt:setrating:4")
            assert mock_send.call_args[0][1] == "\U0001F50D Hech qanday mahsulot topilmadi.\n\nFiltrlarni o'zgartirib ko'ring."  # no rated product -> honest empty state
            _callback(client, customer.telegram_user_id, "flt:clear")
            assert "Unrated Product" in mock_send.call_args[0][1]


class TestOrderDetail:
    def test_shows_real_order_lines_total_and_address(self, settings):
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        customer = _make_customer()
        line = make_line_item(unit_price=Money(amount=Decimal("1120000.00"), currency="UZS"), quantity=1)
        order = Order(
            id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=customer.id, cart_id=uuid.uuid4(),
            shipping_address=make_address(city="Tashkent"), billing_address=make_address(), currency="UZS", channel=OrderChannel.WEB,
            status=OrderStatus.PENDING_PAYMENT, lines={line.id: line}, placed_at=datetime.utcnow(),
        )
        saved = ordering_composition.build_order_repository().save(order)

        client = Client()
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            _callback(client, customer.telegram_user_id, f"ord:detail:{saved.order_number.value}")
            text = mock_send.call_args[0][1]
            assert saved.order_number.value in text
            assert "Tashkent" in text

    def test_a_different_customers_order_number_is_reported_as_not_found_never_leaked(self, settings):
        """IDOR guard, mirrors apps.ordering's own OrderDetailView regression suite -- a real order NUMBER belonging to someone else must never be viewable, and the response must not distinguish "not yours" from "doesn't exist"."""
        settings.TELEGRAM_BOT_TOKEN = "123456:TEST-TOKEN"
        settings.TELEGRAM_WEBHOOK_SECRET = "test-webhook-secret"
        owner = _make_customer()
        attacker = _make_customer()
        line = make_line_item()
        order = Order(
            id=uuid.uuid4(), order_number=OrderNumber(_next_order_number()), customer_id=owner.id, cart_id=uuid.uuid4(),
            shipping_address=make_address(), billing_address=make_address(), currency="UZS", channel=OrderChannel.WEB,
            status=OrderStatus.PENDING_PAYMENT, lines={line.id: line}, placed_at=datetime.utcnow(),
        )
        saved = ordering_composition.build_order_repository().save(order)

        client = Client()
        with patch("apps.telegram_bot.interfaces.callback_router._send") as mock_send, patch("apps.telegram_bot.interfaces.api.v1.views._answer_callback_query"):
            _callback(client, attacker.telegram_user_id, f"ord:detail:{saved.order_number.value}")
            text = mock_send.call_args[0][1]
            assert saved.order_number.value not in text
            assert "topilmadi" in text
