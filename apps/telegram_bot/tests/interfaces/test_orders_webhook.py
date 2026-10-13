"""
Phase 15F: the separate Orders Bot's own webhook
(/api/v1/telegram/orders-webhook) -- a genuinely different bot (own
@username/token) from the customer-facing bot's /api/v1/telegram/webhook,
authenticated with its own secret (TELEGRAM_ORDERS_WEBHOOK_SECRET).
Mirrors test_webhook.py's own security-test shape for the customer
webhook, plus a manager-action integration test proving the shared
handle_callback dispatcher (see test_orders_channel.py) works
identically when reached through this new route.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

ORDERS_WEBHOOK_URL = "/api/v1/telegram/orders-webhook"
TEST_ORDERS_SECRET = "test-orders-webhook-secret-only-not-real"


def _post(client, payload, secret=TEST_ORDERS_SECRET):
    headers = {}
    if secret is not None:
        headers["HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN"] = secret
    return client.post(ORDERS_WEBHOOK_URL, data=json.dumps(payload), content_type="application/json", **headers)


class TestOrdersWebhookSecurity:
    def test_wrong_secret_rejected(self, settings):
        settings.TELEGRAM_ORDERS_WEBHOOK_SECRET = TEST_ORDERS_SECRET
        r = _post(Client(), {}, secret="wrong-secret")
        assert r.status_code == 403

    def test_missing_secret_header_rejected(self, settings):
        settings.TELEGRAM_ORDERS_WEBHOOK_SECRET = TEST_ORDERS_SECRET
        r = _post(Client(), {}, secret=None)
        assert r.status_code == 403

    def test_get_request_rejected(self, settings):
        settings.TELEGRAM_ORDERS_WEBHOOK_SECRET = TEST_ORDERS_SECRET
        r = Client().get(ORDERS_WEBHOOK_URL)
        assert r.status_code == 405

    def test_malformed_json_body_does_not_crash(self, settings):
        settings.TELEGRAM_ORDERS_WEBHOOK_SECRET = TEST_ORDERS_SECRET
        r = Client().post(ORDERS_WEBHOOK_URL, data="not-json{{{", content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=TEST_ORDERS_SECRET)
        assert r.status_code == 200

    def test_unconfigured_secret_rejects_everything(self, settings):
        settings.TELEGRAM_ORDERS_WEBHOOK_SECRET = None
        r = _post(Client(), {}, secret="anything")
        assert r.status_code == 403

    def test_customer_bot_secret_does_not_authenticate_the_orders_webhook(self, settings):
        """The two bots' secrets are independent -- a customer-webhook secret must never authenticate the orders webhook, or vice versa."""
        settings.TELEGRAM_WEBHOOK_SECRET = "customer-secret"
        settings.TELEGRAM_ORDERS_WEBHOOK_SECRET = TEST_ORDERS_SECRET
        r = _post(Client(), {}, secret="customer-secret")
        assert r.status_code == 403

    def test_non_callback_update_is_a_safe_noop(self, settings):
        settings.TELEGRAM_ORDERS_WEBHOOK_SECRET = TEST_ORDERS_SECRET
        r = _post(Client(), {"message": {"chat": {"id": 1}, "from": {"id": 1}, "text": "hello"}})
        assert r.status_code == 200


class TestOrdersWebhookManagerAction:
    def _make_priced_product(self, unit_amount=Decimal("50000.00")):
        from apps.products.infrastructure import models as products_orm
        from apps.pricing.infrastructure import models as pricing_orm

        category = products_orm.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
        products_orm.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="uz", name="Protein", slug=f"protein-{uuid.uuid4().hex[:8]}")
        product = products_orm.Product.objects.create(id=uuid.uuid4(), status="published", category=category)
        products_orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Orders Webhook Test Product", slug=f"orders-webhook-test-{uuid.uuid4().hex[:8]}")
        variant = products_orm.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", status="active", is_default=True)
        price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
        pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant.id, base_price_amount=unit_amount)
        return variant

    def _create_confirmed_cart_order(self, settings, telegram_id, phone_suffix):
        from apps.identity.infrastructure import models as identity_orm

        settings.TELEGRAM_WEBHOOK_SECRET = "customer-secret-for-cart-flow"
        variant = self._make_priced_product()
        user = identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99892{phone_suffix:07d}", full_name="Orders Webhook Test", status="active", telegram_user_id=telegram_id)

        client = Client()
        customer_webhook_url = "/api/v1/telegram/webhook"

        def _customer_callback(data):
            return {"callback_query": {"id": "cbq", "from": {"id": telegram_id}, "message": {"chat": {"id": telegram_id}, "message_id": "1"}, "data": data}}

        def _customer_post(payload):
            return client.post(customer_webhook_url, data=json.dumps(payload), content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="customer-secret-for-cart-flow")

        _customer_post(_customer_callback(f"cart:add:{variant.id}"))
        _customer_post(_customer_callback("checkout:start"))
        _customer_post({"message": {"chat": {"id": telegram_id}, "from": {"id": telegram_id}, "location": {"latitude": 41.3111, "longitude": 69.2797}}})
        _customer_post(_customer_callback("checkout:confirm"))

        from apps.ordering.infrastructure import models as ordering_orm
        order = ordering_orm.OrderModel.objects.get(customer_id=user.id)
        return user, order

    def test_authorized_staff_can_confirm_order_via_the_orders_webhook(self, settings):
        """Proves the separate Orders Bot's own webhook route reuses the exact same, already-tested manager-action dispatcher (callback_router.handle_callback) the customer webhook uses -- not a second, divergent implementation."""
        settings.TELEGRAM_ORDERS_WEBHOOK_SECRET = TEST_ORDERS_SECRET
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        user, order = self._create_confirmed_cart_order(settings, 800700100, 20)
        staff_id = 800700101
        TelegramStaffMember.objects.create(telegram_user_id=staff_id, full_name="Test Manager", is_active=True)

        callback = {"callback_query": {"id": "cbq", "from": {"id": staff_id}, "message": {"chat": {"id": staff_id}, "message_id": "1"}, "data": f"manager:confirm:{order.id}"}}
        r = _post(Client(), callback)
        assert r.status_code == 200

        order.refresh_from_db()
        assert order.status == "confirmed"

    def test_answer_callback_query_uses_the_orders_bot_token_not_the_customer_bot_token(self, settings):
        """Real, closed gap this phase fixes: answering the callback (to clear Telegram's own loading spinner) must hit the Orders Bot's own answerCallbackQuery endpoint -- the customer bot's token has no authority over a callback that arrived on the orders bot's webhook."""
        settings.TELEGRAM_ORDERS_WEBHOOK_SECRET = TEST_ORDERS_SECRET
        settings.TELEGRAM_BOT_TOKEN = "111:customer-bot-token"
        settings.TELEGRAM_ORDERS_BOT_TOKEN = "222:orders-bot-token"
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        user, order = self._create_confirmed_cart_order(settings, 800700102, 21)
        staff_id = 800700103
        TelegramStaffMember.objects.create(telegram_user_id=staff_id, full_name="Test Manager", is_active=True)

        callback = {"callback_query": {"id": "cbq-answer-test", "from": {"id": staff_id}, "message": {"chat": {"id": staff_id}, "message_id": "1"}, "data": f"manager:confirm:{order.id}"}}
        with patch("requests.post") as mock_post:
            r = _post(Client(), callback)
        assert r.status_code == 200
        assert mock_post.called
        called_url = mock_post.call_args.args[0]
        assert "222:orders-bot-token" in called_url
        assert "111:customer-bot-token" not in called_url
