"""Orders / Analytics bots for branch owners: who sees what, the premium sale post, exactly-once owner feeds, store chats."""
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

pytestmark = [pytest.mark.django_db]


@pytest.fixture
def tg(settings, monkeypatch):
    """Both staff bots 'live', every Telegram call recorded instead of sent."""
    from apps.telegram_bot.infrastructure import rich as R

    settings.NUTRIZONE_TELEGRAM_GATEWAY = "live"
    settings.TELEGRAM_ORDERS_BOT_TOKEN = "1:orders"
    settings.TELEGRAM_ANALYTICS_BOT_TOKEN = "2:analytics"
    settings.TELEGRAM_ORDERS_CHAT_ID = "-100777"
    settings.TELEGRAM_ANALYTICS_CHAT_IDS = ""
    calls = []

    def fake_api(token, method, *, data=None, json_body=None, files=None):
        payload = dict(json_body or data or {})
        if "rich_message" in payload:
            payload["html"] = json.loads(payload["rich_message"])["html"]
        calls.append((token, method, payload))
        return {"message_id": len(calls)}

    monkeypatch.setattr(R, "_api", fake_api)
    return calls


def _owner(tg_id: int, store_name: str = "Test Olmazor"):
    from apps.identity.infrastructure.models import User
    from apps.stores.infrastructure.models import Store

    user = User.objects.create(phone_number=f"+99890{tg_id % 10_000_000:07d}", full_name="Ega Egayev", telegram_user_id=tg_id, status="active")
    store = Store.objects.create(name=store_name, slug=f"s-{uuid.uuid4().hex[:8]}", owner=user, kind="store", status="active", color="#2D8CFF")
    return user, store


def _subscribe(bot: str, tg_id: int, started_ago=timedelta(hours=1)):
    from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber

    sub = TelegramBotSubscriber.objects.create(bot=bot, chat_id=tg_id, telegram_user_id=tg_id)
    TelegramBotSubscriber.objects.filter(pk=sub.pk).update(started_at=timezone.now() - started_ago)
    return sub


def _sale(store, coins=Decimal("0"), payments=None, customer=None):
    from apps.pos.infrastructure.models import SaleLineItemModel, SaleModel

    sale = SaleModel.objects.create(branch_id=store.id, cashier_id=uuid.uuid4(), status="completed", channel="store", completed_at=timezone.now() - timedelta(minutes=2),
                                    coins_redeemed=coins, payments=payments or [{"method": "cash", "amount": str(Decimal("300000") - coins)}], customer_id=customer,
                                    receipt_number=f"NZ-{uuid.uuid4().hex[:6]}")
    SaleLineItemModel.objects.create(sale=sale, product_id=uuid.uuid4(), quantity=2, unit_price_amount=Decimal("150000"), unit_price_currency="UZS")
    return sale


class TestScope:
    def test_owner_sees_only_their_branch_and_strangers_nothing(self, tg):
        from apps.telegram_bot.infrastructure import staff_access

        _owner(700001, "Mening filialim")
        _owner(700002, "Boshqa filial")
        sc = staff_access.scope("analytics", 700001)
        assert sc.allowed and not sc.all_access and [s.name for s in sc.stores] == ["Mening filialim"]
        assert not staff_access.scope("analytics", 700099).allowed

    def test_allowlist_sees_every_branch(self, tg, settings):
        from apps.telegram_bot.infrastructure import staff_access

        _owner(700003, "A")
        settings.TELEGRAM_ANALYTICS_CHAT_IDS = "555"
        sc = staff_access.scope("analytics", 555)
        assert sc.all_access and "A" in [s.name for s in sc.stores]


class TestSalePost:
    def test_coins_and_money_split_cashier_branch_and_basket(self, tg):
        from apps.telegram_bot.infrastructure import orders_rich

        user, store = _owner(700010, "Olmazor")
        sale = _sale(store, coins=Decimal("50000"), payments=[{"method": "cash", "amount": "150000"}, {"method": "uzcard", "amount": "100000"}], customer=user.id)
        doc, keyboard = orders_rich.sale_doc(sale.id)
        html = doc.html
        assert "Olmazor" in html and "Kassa savdosi" in html and "head" in doc.images
        assert "NutriZone Coins (17%)" in html and "50 000" in html  # 50 000 of 300 000 paid with coins
        assert "Naqd" in html and "150 000" in html and "Uzcard" in html and "100 000" in html
        assert "<table" in html and "2" in html and "300 000 so&#x27;m" in html.replace("so'm", "so&#x27;m")
        assert "Ega Egayev" in html


class TestOwnerFeeds:
    def test_sale_goes_to_the_branch_owner_once(self, tg):
        from apps.telegram_bot.infrastructure import store_posts

        _user, store = _owner(700020, "Yunusobod")
        _subscribe("orders", 700020)
        other_owner, other = _owner(700021, "Chilonzor")
        _subscribe("orders", 700021)
        _sale(store)
        store_posts.orders_feed()
        store_posts.orders_feed()  # second run: nothing new
        to_owner = [c for c in tg if c[1] == "sendRichMessage" and c[2]["chat_id"] == "700020"]
        to_other = [c for c in tg if c[1] == "sendRichMessage" and c[2]["chat_id"] == "700021"]
        assert len(to_owner) == 1 and "Yunusobod" in to_owner[0][2]["html"]
        assert to_other == []

    def test_only_what_happened_after_they_started(self, tg):
        from apps.telegram_bot.infrastructure import store_posts

        _user, store = _owner(700030)
        _sale(store)
        _subscribe("orders", 700030, started_ago=timedelta(seconds=0))
        store_posts.orders_feed()
        assert not [c for c in tg if c[1] == "sendRichMessage"]

    def test_blocked_bot_deactivates_the_subscriber(self, tg, monkeypatch):
        from apps.telegram_bot.infrastructure import rich as R
        from apps.telegram_bot.infrastructure import store_posts
        from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber, TelegramStorePost

        _user, store = _owner(700040)
        _subscribe("orders", 700040)
        _sale(store)
        monkeypatch.setattr(R, "_api", lambda *a, **k: (_ for _ in ()).throw(R.RichSendError("sendRichMessage: Forbidden: bot was blocked by the user")))
        store_posts.orders_feed()
        assert TelegramBotSubscriber.objects.get(bot="orders", chat_id=700040).is_active is False
        assert not TelegramStorePost.objects.exists()  # released, nothing marked as delivered

    def test_unanswered_store_chat_reaches_the_owner(self, tg):
        from apps.chat.infrastructure.models import ConversationModel, MessageModel, ParticipantModel
        from apps.identity.infrastructure.models import User
        from apps.telegram_bot.infrastructure import store_posts

        _owner_user, store = _owner(700050, "Sergeli")
        _subscribe("analytics", 700050, started_ago=timedelta(hours=2))
        customer = User.objects.create(phone_number="+998901234500", full_name="Xaridor", status="active")
        conv = ConversationModel.objects.create(conversation_type="customer_sales", status="open", store_id=store.id)
        ParticipantModel.objects.create(conversation_id=conv.id, user_id=customer.id, role="customer", joined_at=timezone.now())
        msg = MessageModel.objects.create(conversation_id=conv.id, sender_id=customer.id, message_type="text", content="Protein bormi?")
        MessageModel.objects.filter(pk=msg.pk).update(created_at=timezone.now() - timedelta(minutes=30))
        store_posts.store_chats_feed()
        store_posts.store_chats_feed()
        alerts = [c for c in tg if c[1] == "sendRichMessage" and c[2]["chat_id"] == "700050"]
        assert len(alerts) == 1 and "Protein bormi?" in alerts[0][2]["html"] and "Sergeli" in alerts[0][2]["html"]


class TestOrdersBotStart:
    def test_start_registers_and_lists_today_for_the_owner(self, tg):
        from apps.telegram_bot.infrastructure import orders_bot
        from apps.telegram_bot.infrastructure.models import TelegramBotSubscriber

        _user, store = _owner(700060, "Qo'yliq")
        _sale(store)
        handled = orders_bot.handle_update({"message": {"chat": {"id": 700060, "type": "private"}, "from": {"id": 700060, "first_name": "Ega"}, "text": "/start"}})
        assert handled and TelegramBotSubscriber.objects.filter(bot="orders", chat_id=700060).exists()
        htmls = [c[2]["html"] for c in tg if c[1] == "sendRichMessage"]
        assert any("Qo&#x27;yliq" in h or "Qo'yliq" in h for h in htmls) and any("Kassa savdolari" in h and "300 000" in h for h in htmls)

    def test_stranger_gets_only_the_chat_id(self, tg):
        from apps.telegram_bot.infrastructure import orders_bot

        orders_bot.handle_update({"message": {"chat": {"id": 700099, "type": "private"}, "from": {"id": 700099}, "text": "/start"}})
        (_t, method, payload), = [c for c in tg if c[1] == "sendRichMessage"]
        assert "700099" in payload["html"] and "so'm" not in payload["html"]
