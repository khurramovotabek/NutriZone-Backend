"""
Support-desk automation: working hours, the out-of-hours auto-reply (once per 12 h), the staff Telegram alert for
unanswered chats (once per waiting message), the 1–5 ★ rating asked on every closing (a reused support chat reopens
when the customer writes again), product / order cards, and the API refusing SYSTEM messages from clients.
"""
from __future__ import annotations

import datetime
import json
import uuid
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.chat.domain.enums import MessageType
from apps.chat.infrastructure import automation, composition
from apps.chat.infrastructure import models as orm
from apps.chat.tests.interfaces.test_inbox_premium import _client
from apps.chat.tests.interfaces.test_realtime_and_store_chat import _make_user, _permissive_rbac  # noqa: F401
from apps.notifications.infrastructure.models import NotificationModel

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.integration]
TZ = automation.TZ


def _at(hour: int, weekday: int = 2):
    """A Tashkent datetime on a given weekday (0 = Monday) at `hour`."""
    base = datetime.datetime(2026, 10, 5, tzinfo=TZ)  # a Monday
    return base + datetime.timedelta(days=weekday, hours=hour)


def _settings(**kw):
    cfg = orm.ChatSettings.load()
    for k, v in kw.items():
        setattr(cfg, k, v)
    cfg.save()
    return cfg


def _support(monkeypatch, customer):
    return _client(monkeypatch, customer).post("/api/v1/chat/conversations", {"conversation_type": "customer_support", "opener_role": "customer"}, format="json").json()["data"]


def _staff():
    user = get_user_model().objects.create(username=f"op_{uuid.uuid4().hex[:6]}", is_staff=True, is_superuser=True, first_name="Operator")
    c = Client()
    c.force_login(user)
    return c


class TestWorkingHours:
    def test_open_closed_and_overnight(self):
        cfg = _settings(work_start=datetime.time(9), work_end=datetime.time(21), work_days=[0, 1, 2, 3, 4, 5])
        assert automation.is_open(_at(10), cfg) and not automation.is_open(_at(22), cfg) and not automation.is_open(_at(10, weekday=6), cfg)
        night = _settings(work_start=datetime.time(20), work_end=datetime.time(2))
        assert automation.is_open(_at(23), night) and automation.is_open(_at(1), night) and not automation.is_open(_at(12), night)
        assert automation.hours_label(cfg) == "Du–Sh 09:00–21:00"


class TestAutoReply:
    def test_out_of_hours_gets_one_system_reply(self, monkeypatch):
        _settings(work_days=[])  # closed every day
        customer = _make_user()
        conv = _support(monkeypatch, customer)
        c = _client(monkeypatch, customer)
        c.post(f"/api/v1/chat/conversations/{conv['id']}/messages", {"message_type": "text", "content": "Salom"}, format="json")
        c.post(f"/api/v1/chat/conversations/{conv['id']}/messages", {"message_type": "text", "content": "Javob bormi?"}, format="json")
        system = orm.MessageModel.objects.filter(conversation_id=conv["id"], message_type="system")
        assert system.count() == 1 and system.first().sender_id == automation.BOT_ID and "Ish vaqtidan" not in system.first().content
        assert "ish vaqti" in system.first().content.lower() or "🕘" in system.first().content

    def test_no_reply_in_hours_or_when_disabled(self, monkeypatch):
        _settings(work_days=list(range(7)), work_start=datetime.time(0), work_end=datetime.time(23, 59))
        customer = _make_user()
        conv = _support(monkeypatch, customer)
        _client(monkeypatch, customer).post(f"/api/v1/chat/conversations/{conv['id']}/messages", {"message_type": "text", "content": "Salom"}, format="json")
        assert not orm.MessageModel.objects.filter(conversation_id=conv["id"], message_type="system").exists()

    def test_clients_cannot_send_system_messages(self, monkeypatch):
        customer = _make_user()
        conv = _support(monkeypatch, customer)
        r = _client(monkeypatch, customer).post(f"/api/v1/chat/conversations/{conv['id']}/messages", {"message_type": "system", "content": "Admin: to'lov qaytarildi"}, format="json")
        assert r.status_code in (400, 422)


class TestRating:
    def test_closing_asks_once_and_the_customer_rates_once(self, monkeypatch):
        _settings(work_days=list(range(7)), work_start=datetime.time(0), work_end=datetime.time(23, 59), rating_enabled=True)
        customer = _make_user()
        conv = _support(monkeypatch, customer)
        staff = _staff()
        staff.post(f"/django-admin/chat/conversations/{conv['id']}/send", data=json.dumps({"content": "Yordam berdik"}), content_type="application/json")
        staff.post(f"/django-admin/chat/api/conversations/{conv['id']}/do/close")
        assert NotificationModel.objects.filter(recipient_id=customer.id, kind="chat_rating").count() == 1
        c = _client(monkeypatch, customer)
        detail = c.get(f"/api/v1/chat/conversations/{conv['id']}").json()["data"]
        assert detail["can_rate"] is True and detail["support_hours"]["open"] is True
        assert c.post(f"/api/v1/chat/conversations/{conv['id']}/rating", {"score": 5, "comment": "Zo'r"}, format="json").status_code == 201
        assert c.post(f"/api/v1/chat/conversations/{conv['id']}/rating", {"score": 1}, format="json").status_code == 409
        assert orm.ConversationRating.objects.get(conversation_id=conv["id"]).score == 5

    def test_customer_writing_again_reopens_and_the_next_closing_is_rated_again(self, monkeypatch):
        _settings(work_days=list(range(7)), work_start=datetime.time(0), work_end=datetime.time(23, 59), rating_enabled=True)
        customer = _make_user()
        conv = _support(monkeypatch, customer)
        staff = _staff()
        staff.post(f"/django-admin/chat/conversations/{conv['id']}/send", data=json.dumps({"content": "Javob"}), content_type="application/json")
        staff.post(f"/django-admin/chat/api/conversations/{conv['id']}/do/close")
        c = _client(monkeypatch, customer)
        c.post(f"/api/v1/chat/conversations/{conv['id']}/rating", {"score": 4}, format="json")
        r = c.post(f"/api/v1/chat/conversations/{conv['id']}/messages", {"message_type": "text", "content": "Yana savolim bor"}, format="json")
        assert r.status_code == 201 and orm.ConversationModel.objects.get(pk=conv["id"]).status == "open"
        assert c.post(f"/api/v1/chat/conversations/{conv['id']}/rating", {"score": 2}, format="json").status_code == 409  # open again
        staff.post(f"/django-admin/chat/conversations/{conv['id']}/send", data=json.dumps({"content": "Hal qildik"}), content_type="application/json")
        staff.post(f"/django-admin/chat/api/conversations/{conv['id']}/do/close")
        assert c.post(f"/api/v1/chat/conversations/{conv['id']}/rating", {"score": 3}, format="json").status_code == 201
        assert orm.ConversationRating.objects.filter(conversation_id=conv["id"]).count() == 2


class TestAlert:
    def test_waiting_chat_is_posted_once(self, monkeypatch, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = "-100123"
        _settings(alert_enabled=True, alert_after_minutes=10, alert_only_work_hours=False)
        customer = _make_user(full_name="Sardor")
        conv = _support(monkeypatch, customer)
        msg = composition.build_send_message(customer.id).execute(conversation_id=uuid.UUID(conv["id"]), sender_id=customer.id, message_type=MessageType.TEXT, content="Buyurtmam qayerda?")
        orm.MessageModel.objects.filter(pk=msg.id).update(created_at=timezone.now() - datetime.timedelta(minutes=15))
        gateway = mock.Mock()
        with mock.patch("apps.notifications.infrastructure.composition.build_orders_telegram_gateway", return_value=gateway):
            assert automation.alert_waiting()["sent"] == 1
            assert automation.alert_waiting()["sent"] == 0  # once per waiting message
        text = gateway.send_message_with_keyboard.call_args[0][1]
        assert "Sardor" in text and "Buyurtmam qayerda?" in text


class TestCards:
    def test_order_card_only_for_the_chats_own_customer(self, monkeypatch):
        from apps.ordering.infrastructure.models import OrderModel

        customer, other = _make_user(), _make_user()
        conv = _support(monkeypatch, customer)

        def order(owner):
            return OrderModel.objects.create(order_number=f"ORD-{uuid.uuid4().hex[:6].upper()}", customer_id=owner.id, currency="UZS", status="processing",
                                             shipping_recipient_name="A", shipping_line1="B", shipping_city="Toshkent", shipping_country_code="UZ",
                                             billing_recipient_name="A", billing_line1="B", billing_city="Toshkent", billing_country_code="UZ")

        c = _client(monkeypatch, customer)
        mine = c.post(f"/api/v1/chat/conversations/{conv['id']}/messages", {"message_type": "card", "content": f"order:{order(customer).id}"}, format="json")
        assert mine.status_code == 201 and mine.json()["data"]["card"]["kind"] == "order" and mine.json()["data"]["card"]["status_label"] == "Yig'ilmoqda"
        theirs = c.post(f"/api/v1/chat/conversations/{conv['id']}/messages", {"message_type": "card", "content": f"order:{order(other).id}"}, format="json")
        assert theirs.status_code == 403

    def test_desk_sends_a_product_card_and_counts_quick_replies(self, monkeypatch):
        from apps.products.infrastructure.models import Product, ProductTranslation

        customer = _make_user()
        conv = _support(monkeypatch, customer)
        product = Product.objects.create(status="published")
        ProductTranslation.objects.create(product=product, locale_code="uz", name="Kreatin Monohidrat", slug=f"kreatin-{uuid.uuid4().hex[:6]}")
        staff = _staff()
        found = staff.get("/django-admin/chat/api/cards?q=Kreatin").json()["data"]
        assert found[0]["title"] == "Kreatin Monohidrat"
        r = staff.post(f"/django-admin/chat/conversations/{conv['id']}/send", data=json.dumps({"kind": "card", "content": f"product:{product.id}"}), content_type="application/json")
        assert r.status_code == 201 and r.json()["data"]["messages"][0]["card"]["title"] == "Kreatin Monohidrat"
        q = orm.ChatQuickReply.objects.create(title="Salom", text="Assalomu alaykum!")
        staff.post(f"/django-admin/chat/conversations/{conv['id']}/send", data=json.dumps({"content": q.text, "quick_id": q.pk}), content_type="application/json")
        q.refresh_from_db()
        assert q.uses == 1


class TestAdminPages:
    @pytest.mark.parametrize("url", ["/django-admin/chat/chatquickreply/", "/django-admin/chat/chatquickreply/add/", "/django-admin/chat/conversationrating/", "/django-admin/chat/"])
    def test_render(self, url):
        assert _staff().get(url).status_code == 200

    def test_settings_page_saves(self):
        staff = _staff()
        r = staff.get("/django-admin/chat/chatsettings/")
        assert r.status_code == 302
        data = {"work_start": "08:30", "work_end": "20:00", "days": ["0", "1", "2", "3", "4"], "auto_reply_enabled": "on", "reply_uz": "Ertalab javob beramiz", "reply_ru": "", "reply_en": "",
                "alert_enabled": "on", "alert_after_minutes": "15", "rating_enabled": "on", "delivery_days": "3"}
        assert staff.post(r["Location"], data).status_code == 302
        cfg = orm.ChatSettings.load()
        assert cfg.work_days == [0, 1, 2, 3, 4] and cfg.alert_after_minutes == 15 and cfg.auto_reply_text == {"uz": "Ertalab javob beramiz"} and not cfg.alert_only_work_hours and cfg.delivery_days == 3 and not cfg.order_bot_enabled


def _order(owner, status="processing"):
    from apps.ordering.infrastructure.models import OrderModel

    return OrderModel.objects.create(order_number=f"ORD-{uuid.uuid4().hex[:10].upper()}", customer_id=owner.id, currency="UZS", status=status,
                                     shipping_recipient_name="A", shipping_line1="B", shipping_city="Toshkent", shipping_country_code="UZ",
                                     billing_recipient_name="A", billing_line1="B", billing_city="Toshkent", billing_country_code="UZ")


def _open_all_day(**kw):
    return _settings(work_days=list(range(7)), work_start=datetime.time(0), work_end=datetime.time(23, 59), **kw)


class TestQuickReplyVariables:
    def test_render_fills_known_and_reports_missing(self):
        text, missing = automation.render_template("Salom, {ism}! {buyurtma_raqami} — {noma'lum}", {"ism": "Aziz", "buyurtma_raqami": None})
        assert text == "Salom, Aziz! {buyurtma_raqami} — {noma'lum}" and missing == ["buyurtma_raqami"]

    def test_desk_fills_variables_and_refuses_unfilled_ones(self, monkeypatch):
        _open_all_day()
        customer = _make_user(full_name="Aziz Karimov")
        conv = _support(monkeypatch, customer)
        staff = _staff()
        r = staff.post(f"/django-admin/chat/conversations/{conv['id']}/send", data=json.dumps({"content": "{ism}, {buyurtma_raqami} yo'lda"}), content_type="application/json")
        assert r.status_code == 422 and r.json()["error"]["missing"] == ["buyurtma_raqami"]
        order = _order(customer)
        data = staff.get(f"/django-admin/chat/api/conversations/{conv['id']}").json()["data"]
        assert data["vars"]["ism"] == "Aziz" and data["vars"]["buyurtma_raqami"] == order.order_number and data["vars"]["yetkazish_sanasi"]
        r = staff.post(f"/django-admin/chat/conversations/{conv['id']}/send", data=json.dumps({"content": "{ism}, {buyurtma_raqami} yo'lda"}), content_type="application/json")
        assert r.status_code == 201 and r.json()["data"]["messages"][0]["content"] == f"Aziz, {order.order_number} yo'lda"

    def test_quick_reply_form_rejects_unknown_variables(self):
        staff = _staff()
        r = staff.post("/django-admin/chat/chatquickreply/add/", {"title": "X", "text": "Salom {imya}", "sort_order": 0, "is_active": "on"})
        assert r.status_code == 200 and "Noma&#x27;lum o&#x27;zgaruvchi" in r.content.decode() and not orm.ChatQuickReply.objects.filter(title="X").exists()


class TestOrderBot:
    def test_where_is_my_order_gets_the_card_and_stays_waiting(self, monkeypatch):
        _open_all_day()
        customer = _make_user()
        order = _order(customer)
        conv = _support(monkeypatch, customer)
        c = _client(monkeypatch, customer)
        c.post(f"/api/v1/chat/conversations/{conv['id']}/messages", {"message_type": "text", "content": "Buyurtmam qayerda?"}, format="json")
        bot = orm.MessageModel.objects.filter(conversation_id=conv["id"], sender_id=automation.BOT_ID).order_by("created_at")
        assert [m.message_type for m in bot] == ["system", "card"] and bot[1].content == f"order:{order.id}"
        rows = _staff().get("/django-admin/chat/api/queue?f=waiting").json()["data"]["rows"]
        assert conv["id"] in [r["id"] for r in rows]  # the bot's answer doesn't hide the chat from operators
        c.post(f"/api/v1/chat/conversations/{conv['id']}/messages", {"message_type": "text", "content": "Где мой заказ?"}, format="json")
        assert bot.count() == 2  # not again within 10 minutes

    def test_order_number_only_for_own_orders_and_nothing_without_orders(self, monkeypatch):
        _open_all_day()
        customer, other = _make_user(), _make_user()
        foreign = _order(other)
        conv = _support(monkeypatch, customer)
        c = _client(monkeypatch, customer)
        c.post(f"/api/v1/chat/conversations/{conv['id']}/messages", {"message_type": "text", "content": f"{foreign.order_number} holati qanday?"}, format="json")
        c.post(f"/api/v1/chat/conversations/{conv['id']}/messages", {"message_type": "text", "content": "Buyurtmam qachon keladi?"}, format="json")
        assert not orm.MessageModel.objects.filter(conversation_id=conv["id"], sender_id=automation.BOT_ID).exists()

    def test_intent_detection(self):
        assert automation.asks_order_status("Buyurtmam qayerda?") and automation.asks_order_status("где мой заказ") and automation.asks_order_status("Where is my order?")
        assert not automation.asks_order_status("Buyurtma bermoqchiman") and not automation.asks_order_status("Kreatin bormi?")


class TestLowRating:
    def test_low_score_goes_under_review_alerts_and_is_resolved(self, monkeypatch, settings):
        settings.TELEGRAM_ORDERS_CHAT_ID = "-100123"
        _open_all_day(rating_enabled=True, low_rating_alert=True)
        customer = _make_user(full_name="Nodira")
        conv = _support(monkeypatch, customer)
        staff = _staff()
        staff.post(f"/django-admin/chat/conversations/{conv['id']}/send", data=json.dumps({"content": "Javob"}), content_type="application/json")
        staff.post(f"/django-admin/chat/api/conversations/{conv['id']}/do/close")
        gateway = mock.Mock()
        with mock.patch("apps.notifications.infrastructure.composition.build_orders_telegram_gateway", return_value=gateway):
            assert _client(monkeypatch, customer).post(f"/api/v1/chat/conversations/{conv['id']}/rating", {"score": 2, "comment": "Kech javob"}, format="json").status_code == 201
        text = gateway.send_message_with_keyboard.call_args[0][1]
        assert "2/5" in text and "Nodira" in text and "Kech javob" in text
        assert [r["id"] for r in staff.get("/django-admin/chat/api/queue?f=review").json()["data"]["rows"]] == [conv["id"]]
        r = staff.post(f"/django-admin/chat/api/conversations/{conv['id']}/do/resolve", data=json.dumps({"note": "Qo'ng'iroq qilindi"}), content_type="application/json")
        assert r.status_code == 200 and r.json()["data"]["conversation"]["review"] is None
        rating = orm.ConversationRating.objects.get(conversation_id=conv["id"])
        assert rating.review_status == "resolved" and rating.review_note == "Qo'ng'iroq qilindi" and rating.reviewed_by
        assert staff.post(f"/django-admin/chat/api/conversations/{conv['id']}/do/resolve").status_code == 409

    def test_good_score_is_not_reviewed(self, monkeypatch):
        _open_all_day(rating_enabled=True)
        customer = _make_user()
        conv = _support(monkeypatch, customer)
        staff = _staff()
        staff.post(f"/django-admin/chat/conversations/{conv['id']}/send", data=json.dumps({"content": "Javob"}), content_type="application/json")
        staff.post(f"/django-admin/chat/api/conversations/{conv['id']}/do/close")
        _client(monkeypatch, customer).post(f"/api/v1/chat/conversations/{conv['id']}/rating", {"score": 5}, format="json")
        assert orm.ConversationRating.objects.get(conversation_id=conv["id"]).review_status == ""


class TestOperatorReport:
    def test_night_message_counts_from_opening(self):
        from apps.chat.infrastructure.reports import next_open

        cfg = _settings(work_start=datetime.time(9), work_end=datetime.time(21), work_days=[0, 1, 2, 3, 4, 5])
        assert next_open(_at(23), cfg) == _at(9, weekday=3)  # Wednesday 23:00 → Thursday 09:00
        assert next_open(_at(22, weekday=5), cfg) == _at(9, weekday=7)  # Saturday night → Monday (Sunday off)
        assert next_open(_at(10), cfg) == _at(10)

    def test_operator_row_and_page(self, monkeypatch):
        from apps.chat.infrastructure.reports import operator_report

        _open_all_day()
        customer = _make_user()
        conv = _support(monkeypatch, customer)
        _client(monkeypatch, customer).post(f"/api/v1/chat/conversations/{conv['id']}/messages", {"message_type": "text", "content": "Salom"}, format="json")
        staff = _staff()
        staff.post(f"/django-admin/chat/conversations/{conv['id']}/send", data=json.dumps({"content": "Assalomu alaykum"}), content_type="application/json")
        staff.post(f"/django-admin/chat/api/conversations/{conv['id']}/do/close")
        row = next(r for r in operator_report(7)["rows"] if r["name"] == "Operator")
        assert row["answered"] == 1 and row["closed"] == 1 and row["messages"] == 1 and row["sla"] == 100
        html = staff.get("/django-admin/chat/operators/?days=7").content.decode()
        assert "Operatorlar hisoboti" in html and "Operator" in html
