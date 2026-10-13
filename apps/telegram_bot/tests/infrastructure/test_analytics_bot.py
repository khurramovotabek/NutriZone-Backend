"""NutriZoneAnalyticsBot: Telegram HTML rendering, splitting, access control, de-duplicated scheduled delivery, webhook."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

from apps.platform.infrastructure import business_analytics as ba
from apps.telegram_bot.infrastructure import analytics_bot as bot
from apps.telegram_bot.infrastructure import analytics_report as rep

pytestmark = [pytest.mark.django_db]


@pytest.fixture
def live(settings, monkeypatch):
    settings.NUTRIZONE_TELEGRAM_GATEWAY = "live"
    settings.TELEGRAM_ANALYTICS_BOT_TOKEN = "123:test"
    settings.TELEGRAM_ANALYTICS_CHAT_IDS = "111, -1002222"
    settings.TELEGRAM_ANALYTICS_WEBHOOK_SECRET = "s3cret"
    sent = []

    def fake_call(method, payload):
        sent.append((method, payload))
        return {"message_id": len(sent)}

    monkeypatch.setattr(bot, "call", fake_call)

    from apps.telegram_bot.infrastructure import rich as R

    def fake_api(token, method, *, data=None, json_body=None, files=None):
        payload = dict(json_body or data or {})
        if "rich_message" in payload:  # flatten a rich message into "text" for the assertions below
            payload["text"] = json.loads(payload["rich_message"])["html"]
            payload["files"] = sorted((files or {}).keys())
        if "reply_markup" in payload and isinstance(payload["reply_markup"], str):
            payload["reply_markup"] = json.loads(payload["reply_markup"])
        sent.append((method, payload))
        return {"message_id": len(sent)}

    monkeypatch.setattr(R, "_api", fake_api)
    store: dict = {}

    class FakeRedis:
        def set(self, key, value, nx=False, ex=None):
            if nx and key in store:
                return None
            store[key] = value
            return True

        def delete(self, key):
            store.pop(key, None)

    monkeypatch.setattr("core.caching.redis_client.get_redis_client", lambda: FakeRedis())
    return sent


def _product_sale(name: str, amount: Decimal):
    from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel
    from apps.products.infrastructure.models import Product, ProductTranslation

    product = Product.objects.create()
    ProductTranslation.objects.create(product=product, locale_code="uz", name=name, slug=f"p-{uuid.uuid4().hex[:8]}")
    sale = SaleModel.objects.create(branch_id=uuid.uuid4(), cashier_id=uuid.uuid4(), status="completed", channel="store",
                                    completed_at=timezone.now() - timedelta(minutes=1), payments=[{"method": "cash", "amount": str(amount)}])
    SaleLineItemModel.objects.create(sale=sale, product_id=product.id, quantity=1, unit_price_amount=amount, unit_price_currency="UZS")


class TestRendering:
    def test_formats_escapes_and_marks_trends(self):
        _product_sale("<script>Whey & Co</script>", Decimal("1250000"))
        text = "\n".join(rep.render(ba.build(ba.period("today"))))
        assert "&lt;script&gt;Whey &amp; Co&lt;/script&gt;" in text and "<script>" not in text
        assert "1 250 000 so'm" in text
        assert text.startswith("📊 <b>NUTRIZONE — BUGUNGI PULS</b>")
        assert "NutriZoneAnalyticsBot" in text

    def test_arrows(self):
        assert rep.arrow(ba.change(112, 100)) == "▲ 12%"
        assert rep.arrow(ba.change(90, 100), "kechaga") == "▼ 10% kechaga"
        assert rep.arrow(ba.change(5, 0)) == ""  # no baseline: no fake percentage
        assert rep.arrow(ba.change(5, 0), unit="ta") == "▲ 5 ta"

    def test_only_telegram_html_tags(self):
        import re

        r = ba.build(ba.period("30d"))
        for msg in rep.render(r):
            assert set(re.findall(r"</?([a-z]+)", msg)) <= {"b", "i", "code", "blockquote"}

    def test_split_respects_limit_and_section_boundaries(self):
        blocks = ["A" * 100, "B" * 3000, "C" * 3000, "\n".join(["D" * 50] * 200)]
        parts = rep.split(blocks, limit=3900)
        assert all(len(p) <= 3900 for p in parts)
        assert parts[0].startswith("A") and parts[1].startswith("C")  # B fits with A, C starts a new message
        assert "".join(parts).count("D" * 50) == 200

    def test_store_circles_are_stable(self):
        assert rep.circle("#22C55E") == "🟢" and rep.circle("#2D8CFF") == "🔵" and rep.circle(None) == "⚪"
        assert rep.circle("#000", "online") == "🌐"


class TestAccess:
    def test_unknown_chat_only_gets_its_id(self, live):
        bot.handle_update({"message": {"chat": {"id": 999, "type": "private"}, "from": {"id": 999}, "text": "/bugun"}})
        (method, payload), = live
        assert method == "sendRichMessage" and "999" in payload["text"] and "so'm" not in payload["text"]

    def test_recipient_gets_a_rich_report_with_charts_and_menu(self, live):
        from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel

        sale = SaleModel.objects.create(branch_id=uuid.uuid4(), cashier_id=uuid.uuid4(), status="completed", channel="store",
                                        completed_at=timezone.now() - timedelta(minutes=1), payments=[{"method": "cash", "amount": "250000"}])
        SaleLineItemModel.objects.create(sale=sale, product_id=uuid.uuid4(), quantity=1, unit_price_amount=Decimal("250000"), unit_price_currency="UZS")
        bot.handle_update({"message": {"chat": {"id": 111, "type": "private"}, "from": {"id": 111}, "text": "/bugun@NutriZoneAnalyticsBot"}})
        report = [p for m, p in live if m == "sendRichMessage" and "Bugungi puls" in p["text"]]
        assert report, [m for m, _p in live]
        assert "<table" in report[0]["text"] and "kpi" in report[0]["files"] and "250 000" in report[0]["text"]
        assert report[0]["reply_markup"]["inline_keyboard"]

    def test_button_press(self, live):
        bot.handle_update({"callback_query": {"id": "q1", "data": "an:30kun", "from": {"id": 1}, "message": {"chat": {"id": -1002222}}}})
        assert live[0][0] == "answerCallbackQuery"
        assert any(m == "sendRichMessage" and "30 kun" in p["text"] and "<table" in p["text"] for m, p in live)


class TestScheduled:
    def test_delivered_once_per_period_and_recipient(self, live):
        first = bot.send_scheduled("today")
        assert first["sent"] == 2
        again = bot.send_scheduled("today")
        assert again == {"sent": 0, "skipped": 2, "failed": 0}

    def test_failed_delivery_can_be_retried(self, live, monkeypatch):
        from apps.telegram_bot.infrastructure import rich as R

        def boom(token, method, **kw):
            raise R.RichSendError(f"{method}: Bad Request: chat not found")

        monkeypatch.setattr(R, "_api", boom)
        assert bot.send_scheduled("week")["failed"] == 2
        monkeypatch.setattr(R, "_api", lambda token, method, **kw: {"message_id": 1})
        assert bot.send_scheduled("week")["sent"] == 2

    def test_not_configured_sends_nothing(self, settings):
        settings.TELEGRAM_ANALYTICS_BOT_TOKEN = ""
        assert bot.send_scheduled("today")["reason"] == "not configured"

    def test_setup_creates_three_schedules_without_duplicates(self, settings):
        from django.core.management import call_command
        from django_celery_beat.models import PeriodicTask

        settings.TELEGRAM_ANALYTICS_BOT_TOKEN = ""
        call_command("analytics_bot_setup")
        call_command("analytics_bot_setup")
        rows = PeriodicTask.objects.filter(task="telegram_bot.analytics_report")
        assert rows.count() == 3
        assert sorted(json.loads(r.args)[0] for r in rows) == ["month", "today", "week"]
        assert {r.crontab.timezone.key if hasattr(r.crontab.timezone, "key") else str(r.crontab.timezone) for r in rows} == {"Asia/Tashkent"}


class TestWebhookAndChatAlerts:
    def test_webhook_requires_secret(self, live):
        c = Client()
        url = "/api/v1/telegram/analytics-webhook"
        body = json.dumps({"message": {"chat": {"id": 111, "type": "private"}, "text": "/id"}})
        assert c.post(url, body, content_type="application/json").status_code == 403
        assert c.post(url, body, content_type="application/json", HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="s3cret").status_code == 200
        assert any("111" in p.get("text", "") for _m, p in live)

    def test_waiting_chat_alert_goes_to_analytics_bot(self, live, monkeypatch):
        from apps.chat.infrastructure import automation

        cfg = automation.chat_settings()
        cfg.alert_enabled, cfg.alert_only_work_hours, cfg.alert_after_minutes = True, False, 1
        cfg.save()
        msg = type("M", (), {"pk": uuid.uuid4(), "created_at": timezone.now() - timedelta(minutes=30), "content": "Salom <b>", "message_type": "text"})()
        monkeypatch.setattr(automation, "waiting_conversations", lambda older: [{"conversation_id": uuid.uuid4(), "message": msg, "customer_id": uuid.uuid4()}])
        monkeypatch.setattr(automation, "_log", lambda *a: True)
        result = automation.alert_waiting()
        assert result == {"sent": 1, "via": "analytics"}
        texts = [p["text"] for m, p in live if m == "sendMessage"]
        assert len(texts) == 2 and "Javobsiz chat" in texts[0] and "Salom &lt;b&gt;" in texts[0]

    def test_masked_phone(self):
        u = type("U", (), {"full_name": "Ali", "phone_number": "+998901234567"})()
        assert bot.customer_label(u) == "Ali · +99890•••67"
