"""
POS Terminal sales -> Telegram Orders Channel (pos_sales_channel_subscriber.py).
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from django_celery_beat.models import PeriodicTask

from apps.notifications.infrastructure import composition as notifications_composition

pytestmark = pytest.mark.django_db

ORDERS_CHAT_ID = "-100999888"


class _FakeGateway:
    def __init__(self):
        self.sent_messages = []
        self.sent_photos = []

    def send_message_with_keyboard(self, chat_id, text, keyboard):
        self.sent_messages.append((chat_id, text, keyboard))
        return f"fake-msg-{len(self.sent_messages)}"

    def send_photo(self, chat_id, photo_url, caption, inline_keyboard=None):
        self.sent_photos.append((chat_id, photo_url, caption, inline_keyboard))
        return f"fake-photo-{len(self.sent_photos)}"

    @property
    def all_texts(self):
        return [m[1] for m in self.sent_messages] + [p[2] for p in self.sent_photos]


def _completed_sale(delivery_fee=Decimal("0"), full_name="Aziz Karimov"):
    """A real sale through the real POS services, so its SaleCompleted outbox event is genuine."""
    from apps.identity.infrastructure.models import User
    from apps.pos.infrastructure import composition
    from apps.pos.infrastructure.models import SaleModel
    from apps.products.infrastructure import models as p_models

    product = p_models.Product.objects.create(id=uuid.uuid4(), status="published")
    p_models.ProductTranslation.objects.create(id=uuid.uuid4(), product=product, locale_code="uz", name="Kreatin <250 g>", slug=f"k-{uuid.uuid4().hex[:8]}")
    customer = User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", full_name=full_name)

    actor = uuid.uuid4()
    sale = composition.build_open_sale(actor).execute(branch_id=uuid.uuid4(), cashier_id=actor, customer_id=customer.id)
    composition.build_add_line_item(actor).execute(sale_id=sale.id, product_id=product.id, quantity=2, unit_price_amount=Decimal("180000"), unit_price_currency="UZS")
    composition.build_complete_sale(actor).execute(sale.id)
    if delivery_fee:
        SaleModel.objects.filter(id=sale.id).update(delivery_fee_amount=delivery_fee)
    return sale, customer


def _sync(settings, gateway):
    from apps.telegram_bot.infrastructure.pos_sales_channel_subscriber import sync_pos_sales_channel

    settings.TELEGRAM_ORDERS_CHAT_ID = ORDERS_CHAT_ID
    settings.PUBLIC_BASE_URL = "https://admin.example.test"
    with patch.object(notifications_composition, "build_orders_telegram_gateway", return_value=gateway):
        return sync_pos_sales_channel()


class TestCompletedSalePost:
    def test_posts_completed_sale_marked_as_pos_with_customer_and_totals(self, settings):
        sale, customer = _completed_sale(delivery_fee=Decimal("50000"))
        gateway = _FakeGateway()

        result = _sync(settings, gateway)

        assert result["posted"] == 1
        (text,) = gateway.all_texts
        assert "POS Terminal orqali" in text
        assert "#" + str(sale.id)[:8].upper() in text
        assert customer.full_name in text and customer.phone_number in text
        assert "2 x 180 000 so'm" in text
        assert "Yetkazib berish: 50 000 so'm" in text
        assert "Jami: 410 000 so'm" in text
        assert "Kreatin &lt;250 g&gt;" in text  # product names are HTML-escaped

    def test_never_sends_a_map_or_manager_confirm_buttons(self, settings):
        _completed_sale()
        gateway = _FakeGateway()
        _sync(settings, gateway)

        (chat_id, text, keyboard) = gateway.sent_messages[0]
        assert "maps.google" not in text and "Xaritada" not in text
        buttons = [b for row in keyboard for b in row]
        assert all("callback_data" not in b for b in buttons)
        assert buttons[0]["url"].endswith("/change/")

    def test_replay_does_not_post_twice(self, settings):
        from apps.telegram_bot.infrastructure import models as telegram_orm

        _completed_sale()
        _sync(settings, _FakeGateway())
        telegram_orm.TelegramOrdersChannelCursor.objects.filter(id=2).update(last_processed_created_at=None, last_processed_id=None)

        gateway = _FakeGateway()
        result = _sync(settings, gateway)

        assert result["posted"] == 0
        assert gateway.all_texts == []

    def test_no_channel_configured_is_a_noop(self, settings):
        from apps.telegram_bot.infrastructure.pos_sales_channel_subscriber import sync_pos_sales_channel

        _completed_sale()
        settings.TELEGRAM_ORDERS_CHAT_ID = ""
        assert sync_pos_sales_channel()["skipped_no_channel"] is True


class TestRefundedSalePost:
    def test_refund_posts_a_return_notice(self, settings):
        from apps.pos.infrastructure import composition

        sale, _customer = _completed_sale()
        _sync(settings, _FakeGateway())
        composition.build_refund_sale(uuid.uuid4()).execute(sale.id)

        gateway = _FakeGateway()
        result = _sync(settings, gateway)

        assert result["posted"] == 1
        (text,) = gateway.all_texts
        assert "BUYURTMA QAYTARILDI" in text
        assert "POS Terminal orqali" in text
        assert "360 000 so'm" in text


class TestCursorSafety:
    def test_missing_cursor_starts_at_now_instead_of_replaying_history(self, settings):
        from apps.telegram_bot.infrastructure import models as telegram_orm

        _completed_sale()
        telegram_orm.TelegramOrdersChannelCursor.objects.filter(id=2).delete()

        gateway = _FakeGateway()
        first = _sync(settings, gateway)
        second = _sync(settings, gateway)

        assert first.get("initialized") is True
        assert second["posted"] == 0
        assert gateway.all_texts == []

    def test_online_orders_cursor_is_untouched(self, settings):
        from apps.telegram_bot.infrastructure import models as telegram_orm

        _completed_sale()
        before = telegram_orm.TelegramOrdersChannelCursor.objects.filter(id=1).values_list("last_processed_id", flat=True).first()
        _sync(settings, _FakeGateway())
        after = telegram_orm.TelegramOrdersChannelCursor.objects.filter(id=1).values_list("last_processed_id", flat=True).first()
        assert before == after


def test_pos_sales_channel_sync_is_scheduled_every_30_seconds():
    task = PeriodicTask.objects.get(name="Telegram Orders Channel sync (POS Terminal)")
    assert task.task == "telegram_bot.sync_pos_sales_channel"
    assert task.enabled is True
    assert (task.interval.every, task.interval.period) == (30, "seconds")
