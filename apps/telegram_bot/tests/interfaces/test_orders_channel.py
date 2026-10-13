"""
Phase 15E: Telegram Orders Channel tests.

Every scenario was first verified live via real HTTP requests before
being formalized, matching the discipline established in Phase
15B/15C/15D.
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
ORDERS_CHAT_ID = "-100999888"


class _FakeGateway:
    def __init__(self):
        self.sent_messages = []
        self.sent_photos = []
        self.edited_messages = []

    def send_message(self, chat_id, title, body):
        return "fake-msg-id"

    def send_message_with_keyboard(self, chat_id, text, keyboard):
        self.sent_messages.append((chat_id, text, keyboard))
        return f"fake-channel-msg-{len(self.sent_messages)}"

    def send_photo(self, chat_id, photo_url, caption, inline_keyboard=None):
        self.sent_photos.append((chat_id, photo_url, caption, inline_keyboard))
        return f"fake-channel-photo-{len(self.sent_photos)}"

    def edit_message_text(self, chat_id, message_id, text, inline_keyboard=None):
        self.edited_messages.append((chat_id, message_id, text, inline_keyboard))


def _post(client, payload):
    return client.post(WEBHOOK_URL, data=json.dumps(payload), content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=TEST_SECRET)


def _callback(telegram_user_id, data, message_id="999"):
    return {"callback_query": {"id": "cbq", "from": {"id": telegram_user_id}, "message": {"chat": {"id": telegram_user_id}, "message_id": message_id}, "data": data}}


def _make_priced_product(unit_amount=Decimal("50000.00"), with_image=False):
    from apps.products.infrastructure import models as products_orm
    from apps.pricing.infrastructure import models as pricing_orm

    category = products_orm.Category.objects.create(id=uuid.uuid4(), is_active=True, sort_order=1)
    products_orm.CategoryTranslation.objects.create(id=uuid.uuid4(), category=category, locale_code="uz", name="Protein", slug=f"protein-{uuid.uuid4().hex[:8]}")
    product = products_orm.Product.objects.create(id=uuid.uuid4(), status="published", category=category)
    products_orm.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Channel Test Product", slug=f"channel-test-{uuid.uuid4().hex[:8]}")
    if with_image:
        products_orm.ProductMedia.objects.create(id=uuid.uuid4(), product=product, storage_path=f"products/{uuid.uuid4().hex[:8]}/main.jpg", media_role="primary")
    variant = products_orm.ProductVariant.objects.create(id=uuid.uuid4(), product=product, sku=f"SKU-{uuid.uuid4().hex[:8]}", status="active", is_default=True)
    price_list, _ = pricing_orm.PriceListModel.objects.get_or_create(code="DEFAULT-UZS", defaults={"name": "Default", "currency": "UZS", "status": "active"})
    pricing_orm.PriceListEntryModel.objects.create(price_list=price_list, product_variant_id=variant.id, base_price_amount=unit_amount)
    return category, product, variant


def _register(telegram_user_id, phone_suffix):
    from apps.identity.infrastructure import models as identity_orm

    return identity_orm.User.objects.create(id=uuid.uuid4(), phone_number=f"+99892{phone_suffix:07d}", full_name="Channel Test", status="active", telegram_user_id=telegram_user_id)


def _create_confirmed_cart_order(settings, telegram_id, phone_suffix, unit_amount=Decimal("50000.00"), with_image=False):
    settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
    category, product, variant = _make_priced_product(unit_amount, with_image=with_image)
    user = _register(telegram_id, phone_suffix)
    client = Client()
    _post(client, _callback(telegram_id, f"cart:add:{variant.id}"))
    _post(client, _callback(telegram_id, "checkout:start"))
    _post(client, {"message": {"chat": {"id": telegram_id}, "from": {"id": telegram_id}, "location": {"latitude": 41.3111, "longitude": 69.2797}}})
    _post(client, _callback(telegram_id, "checkout:confirm"))

    from apps.ordering.infrastructure import models as ordering_orm
    order = ordering_orm.OrderModel.objects.get(customer_id=user.id)
    return user, order


class TestOrdersChannelPosting:
    def test_no_channel_configured_is_a_safe_noop(self, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = None
        from apps.telegram_bot.infrastructure.orders_channel_subscriber import sync_orders_channel

        result = sync_orders_channel()
        assert result.get("skipped_no_channel") is True

    def test_new_order_is_posted_to_channel(self, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = ORDERS_CHAT_ID
        from apps.notifications.infrastructure import composition as notifications_composition
        from apps.telegram_bot.infrastructure.orders_channel_subscriber import sync_orders_channel
        from apps.telegram_bot.infrastructure import models as telegram_orm

        user, order = _create_confirmed_cart_order(settings, 800600100, 1)
        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_orders_telegram_gateway", return_value=fake_gateway):
            result = sync_orders_channel()

        assert result["posted"] == 1
        assert len(fake_gateway.sent_messages) == 1
        assert order.order_number in fake_gateway.sent_messages[0][1]
        assert telegram_orm.TelegramOrderChannelMessage.objects.filter(order_id=order.id).exists()

    def test_duplicate_channel_sync_does_not_repost(self, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = ORDERS_CHAT_ID
        from apps.notifications.infrastructure import composition as notifications_composition
        from apps.telegram_bot.infrastructure.orders_channel_subscriber import sync_orders_channel
        from apps.telegram_bot.infrastructure import models as telegram_orm

        user, order = _create_confirmed_cart_order(settings, 800600101, 2)
        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_orders_telegram_gateway", return_value=fake_gateway):
            sync_orders_channel()
            cursor = telegram_orm.TelegramOrdersChannelCursor.objects.get(id=1)
            cursor.last_processed_created_at = None
            cursor.last_processed_id = None
            cursor.save()
            sync_orders_channel()

        assert len(fake_gateway.sent_messages) == 1

    def test_channel_message_includes_real_customer_address_and_location(self, settings):
        """Real, closed gap: the channel message previously showed only order number/total/line count -- no customer name/phone, address, or GPS location."""
        settings.TELEGRAM_ORDERS_CHAT_ID = ORDERS_CHAT_ID
        from apps.notifications.infrastructure import composition as notifications_composition
        from apps.telegram_bot.infrastructure.orders_channel_subscriber import sync_orders_channel

        user, order = _create_confirmed_cart_order(settings, 800600102, 3)
        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_orders_telegram_gateway", return_value=fake_gateway):
            sync_orders_channel()

        assert len(fake_gateway.sent_messages) == 1
        text = fake_gateway.sent_messages[0][1]
        assert order.shipping_recipient_name in text
        assert "41.3111" in text and "69.2797" in text
        assert "maps.google.com" in text
        keyboard = fake_gateway.sent_messages[0][2]
        assert any(b.get("callback_data", "").startswith("manager:confirm:") for row in keyboard for b in row)

    def test_channel_message_sends_a_real_product_photo_when_one_exists(self, settings):
        """Real, closed gap: no product image was ever attached to the channel message, even when the ordered product had a real primary image."""
        settings.TELEGRAM_ORDERS_CHAT_ID = ORDERS_CHAT_ID
        from apps.notifications.infrastructure import composition as notifications_composition
        from apps.telegram_bot.infrastructure.orders_channel_subscriber import sync_orders_channel

        user, order = _create_confirmed_cart_order(settings, 800600103, 4, with_image=True)
        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_orders_telegram_gateway", return_value=fake_gateway):
            result = sync_orders_channel()

        assert result["posted"] == 1
        assert len(fake_gateway.sent_photos) == 1
        assert not fake_gateway.sent_messages  # a real image takes the send_photo path, not send_message_with_keyboard
        chat_id, photo_url, caption, keyboard = fake_gateway.sent_photos[0]
        assert "Channel Test Product" in caption
        assert order.shipping_recipient_name in caption

    def test_channel_message_includes_dashboard_link_when_configured(self, settings):
        """Real, closed gap: the manager had no way to open this order's real dashboard detail page directly from the channel message."""
        settings.TELEGRAM_ORDERS_CHAT_ID = ORDERS_CHAT_ID
        settings.PUBLIC_BASE_URL = "https://nutrizone.uz"
        from apps.notifications.infrastructure import composition as notifications_composition
        from apps.telegram_bot.infrastructure.orders_channel_subscriber import sync_orders_channel

        user, order = _create_confirmed_cart_order(settings, 800600104, 5)
        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_orders_telegram_gateway", return_value=fake_gateway):
            sync_orders_channel()

        keyboard = fake_gateway.sent_messages[0][2]
        expected_url = f"https://nutrizone.uz/django-admin/ordering/ordermodel/{order.id}/change/"
        assert any(b.get("url") == expected_url for row in keyboard for b in row)


class TestManagerAuthorization:
    def test_unauthorized_user_cannot_confirm_order(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        user, order = _create_confirmed_cart_order(settings, 800600200, 3)
        attacker_id = 800600201

        r = _post(Client(), _callback(attacker_id, f"manager:confirm:{order.id}"))
        assert r.status_code == 200

        order.refresh_from_db()
        assert order.status == "pending_payment"

    def test_authorized_staff_can_confirm_order(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        user, order = _create_confirmed_cart_order(settings, 800600202, 4)
        staff_id = 800600203
        TelegramStaffMember.objects.create(telegram_user_id=staff_id, full_name="Test Manager", is_active=True)

        r = _post(Client(), _callback(staff_id, f"manager:confirm:{order.id}"))
        assert r.status_code == 200

        order.refresh_from_db()
        assert order.status == "confirmed"

    def test_authorized_staff_can_cancel_order(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        user, order = _create_confirmed_cart_order(settings, 800600204, 5)
        staff_id = 800600205
        TelegramStaffMember.objects.create(telegram_user_id=staff_id, full_name="Test Manager", is_active=True)

        r = _post(Client(), _callback(staff_id, f"manager:cancel:{order.id}"))
        assert r.status_code == 200

        order.refresh_from_db()
        assert order.status == "cancelled"

    def test_inactive_staff_member_is_rejected(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        user, order = _create_confirmed_cart_order(settings, 800600206, 6)
        staff_id = 800600207
        TelegramStaffMember.objects.create(telegram_user_id=staff_id, full_name="Deactivated Manager", is_active=False)

        r = _post(Client(), _callback(staff_id, f"manager:confirm:{order.id}"))
        assert r.status_code == 200

        order.refresh_from_db()
        assert order.status == "pending_payment"


class TestManagerActionIdempotency:
    def test_double_confirm_click_is_safe_noop_via_domain_state_machine(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        user, order = _create_confirmed_cart_order(settings, 800600300, 7)
        staff_id = 800600301
        TelegramStaffMember.objects.create(telegram_user_id=staff_id, full_name="Test Manager", is_active=True)

        client = Client()
        _post(client, _callback(staff_id, f"manager:confirm:{order.id}"))
        r2 = _post(client, _callback(staff_id, f"manager:confirm:{order.id}"))
        assert r2.status_code == 200

        order.refresh_from_db()
        assert order.status == "confirmed"

    def test_resolved_channel_message_blocks_a_different_action_too(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        settings.TELEGRAM_ORDERS_CHAT_ID = ORDERS_CHAT_ID
        from apps.notifications.infrastructure import composition as notifications_composition
        from apps.telegram_bot.infrastructure.orders_channel_subscriber import sync_orders_channel
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember, TelegramOrderChannelMessage

        user, order = _create_confirmed_cart_order(settings, 800600302, 8)
        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_orders_telegram_gateway", return_value=fake_gateway):
            sync_orders_channel()

            staff_id = 800600303
            TelegramStaffMember.objects.create(telegram_user_id=staff_id, full_name="Test Manager", is_active=True)
            client = Client()
            _post(client, _callback(staff_id, f"manager:confirm:{order.id}"))

            channel_message = TelegramOrderChannelMessage.objects.get(order_id=order.id)
            assert channel_message.resolved_at is not None

            _post(client, _callback(staff_id, f"manager:cancel:{order.id}"))

        order.refresh_from_db()
        assert order.status == "confirmed"

    def test_confirmed_order_message_gets_edited_with_buttons_removed(self, settings):
        settings.TELEGRAM_WEBHOOK_SECRET = TEST_SECRET
        settings.TELEGRAM_ORDERS_CHAT_ID = ORDERS_CHAT_ID
        from apps.notifications.infrastructure import composition as notifications_composition
        from apps.telegram_bot.infrastructure.orders_channel_subscriber import sync_orders_channel
        from apps.telegram_bot.infrastructure.models import TelegramStaffMember

        user, order = _create_confirmed_cart_order(settings, 800600304, 9)
        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_orders_telegram_gateway", return_value=fake_gateway):
            sync_orders_channel()
            staff_id = 800600305
            TelegramStaffMember.objects.create(telegram_user_id=staff_id, full_name="Test Manager", is_active=True)
            _post(Client(), _callback(staff_id, f"manager:confirm:{order.id}"))

        assert len(fake_gateway.edited_messages) == 1
        keyboard = fake_gateway.edited_messages[0][3]
        assert not any(b.get("callback_data", "").startswith("manager:") for row in keyboard for b in row)  # Confirm/Cancel gone
        assert "TASDIQLANDI" in fake_gateway.edited_messages[0][2] and "Mahsulotlar" in fake_gateway.edited_messages[0][2]  # details kept


class TestManagerActionOrderTotalIntegrity:
    def test_channel_message_shows_real_order_total_not_recomputed(self, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = ORDERS_CHAT_ID
        from apps.notifications.infrastructure import composition as notifications_composition
        from apps.telegram_bot.infrastructure.orders_channel_subscriber import sync_orders_channel

        user, order = _create_confirmed_cart_order(settings, 800600400, 10, unit_amount=Decimal("33333.00"))
        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_orders_telegram_gateway", return_value=fake_gateway):
            sync_orders_channel()

        assert "33 333 so'm" in fake_gateway.sent_messages[0][1]


def _pay_with_coins(user, order, coins, extra_discount=Decimal("0")):
    """Mirrors checkout: coins (plus any coupon) are spread into the line's discount_amount, and a SPEND transaction is recorded for the order."""
    from apps.loyalty.infrastructure import models as loyalty_orm
    from apps.ordering.infrastructure import models as ordering_orm

    ordering_orm.OrderLineItemModel.objects.filter(order_id=order.id).update(discount_amount=Decimal(coins) + extra_discount)
    wallet, _ = loyalty_orm.Wallet.objects.get_or_create(user=user)
    loyalty_orm.WalletTransaction.objects.create(wallet=wallet, kind=loyalty_orm.WalletTransactionKind.SPEND, amount=-coins, balance_after=0, order_id=order.id, order_number=order.order_number)


class TestOrdersChannelCoinPayment:
    def _sync(self):
        from apps.notifications.infrastructure import composition as notifications_composition
        from apps.telegram_bot.infrastructure.orders_channel_subscriber import sync_orders_channel

        fake_gateway = _FakeGateway()
        with patch.object(notifications_composition, "build_orders_telegram_gateway", return_value=fake_gateway):
            sync_orders_channel()
        assert len(fake_gateway.sent_messages) == 1
        return fake_gateway.sent_messages[0][1]

    def test_coin_payment_shows_coins_and_cash_split(self, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = ORDERS_CHAT_ID
        user, order = _create_confirmed_cart_order(settings, 800600201, 21)
        _pay_with_coins(user, order, 10000)

        text = self._sync()
        assert "jami 50 000 so'm" in text
        assert "Coins bilan: −10 000 so'm" in text
        assert "Olinadigan summa: 40 000 so'm" in text
        assert "Chegirma" not in text

    def test_coin_payment_with_coupon_lists_the_coupon_discount_separately(self, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = ORDERS_CHAT_ID
        user, order = _create_confirmed_cart_order(settings, 800600202, 22)
        _pay_with_coins(user, order, 10000, extra_discount=Decimal("5000"))

        text = self._sync()
        assert "Chegirma: −5 000 so'm" in text
        assert "jami 45 000 so'm" in text
        assert "Coins bilan: −10 000 so'm" in text
        assert "Olinadigan summa: 35 000 so'm" in text

    def test_order_without_coins_keeps_the_plain_total(self, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = ORDERS_CHAT_ID
        user, order = _create_confirmed_cart_order(settings, 800600203, 23)

        text = self._sync()
        assert "Coins bilan" not in text and "Olinadigan" not in text
        assert "Jami: 50 000 so'm" in text
