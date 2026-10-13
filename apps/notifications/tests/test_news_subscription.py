"""Telegram news subscription: subscribe/unsubscribe, broadcast audience, one-time gift on the first purchase after subscribing, bot screens."""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from apps.identity.infrastructure.models import User
from apps.loyalty.infrastructure.models import LoyaltySettings, Wallet, WalletTransaction
from apps.notifications.infrastructure import subscriptions
from apps.notifications.infrastructure.models import NewsSubscription, NotificationModel
from apps.notifications.infrastructure.notify import audience_queryset

pytestmark = pytest.mark.django_db


def _user(name="Obunachi Test"):
    return User.objects.create(id=uuid.uuid4(), phone_number=f"+99893{uuid.uuid4().int % 10**7:07d}", full_name=name, status="active", language="uz")


def test_subscribe_audience_and_gift_once(django_capture_on_commit_callbacks):
    LoyaltySettings.load()
    LoyaltySettings.objects.filter(pk=1).update(subscribe_gift_coins=7000)
    u, other = _user(), _user("Boshqa")
    with django_capture_on_commit_callbacks(execute=True):
        sub, fresh = subscriptions.subscribe(u.id, source="bot")
    assert fresh and subscriptions.is_subscribed(u.id)
    assert NotificationModel.objects.filter(recipient_id=u.id, kind="news_subscribed").exists()
    assert list(audience_queryset("subscribers")) == [u]

    assert subscriptions.on_purchase(u.id, uuid.uuid4(), "NZ-1", timezone.now() - timedelta(days=1)) == 0  # bought before subscribing
    assert subscriptions.on_purchase(other.id, uuid.uuid4(), "NZ-2") == 0  # not a subscriber
    with django_capture_on_commit_callbacks(execute=True):
        assert subscriptions.on_purchase(u.id, uuid.uuid4(), "NZ-3") == 7000
    assert Wallet.objects.get(user=u).balance == 7000
    assert WalletTransaction.objects.get(wallet__user=u).kind == "adjustment"
    assert NotificationModel.objects.filter(recipient_id=u.id, kind="subscription_gift").exists()
    assert subscriptions.on_purchase(u.id, uuid.uuid4(), "NZ-4") == 0  # never twice

    assert subscriptions.unsubscribe(u.id) and not list(audience_queryset("subscribers"))
    sub2, fresh2 = subscriptions.subscribe(u.id)
    assert fresh2 and sub2.id == sub.id and sub2.gift_granted_at is not None  # re-subscribing doesn't re-open the gift
    assert subscriptions.on_purchase(u.id, uuid.uuid4(), "NZ-5") == 0


def test_bot_news_screen_and_deep_link():
    from apps.telegram_bot.interfaces import news_menu

    u = _user()
    sent = []
    with mock.patch("apps.telegram_bot.interfaces.callback_router._send", side_effect=lambda chat, text, kb=None: sent.append((text, kb))):
        news_menu.show(u, 1, "uz")
        assert "Obuna bo'ling" in sent[-1][0] and sent[-1][1][0][0]["callback_data"] == "news:on"
        news_menu.handle(u, 1, "on", "uz")
        assert "Obuna bo'ldingiz" in sent[-1][0] and sent[-1][1][0][0]["callback_data"] == "news:off"
        news_menu.handle(u, 1, "off", "uz")
        assert "bekor" in sent[-1][0] and not NewsSubscription.objects.get(user=u).is_active
        news_menu.subscribe_from_link(u, 1, "uz")
    assert NewsSubscription.objects.get(user=u).is_active and NewsSubscription.objects.get(user=u).source == "bot"


def test_public_info_endpoint(client, settings):
    settings.TELEGRAM_BOT_USERNAME = "nz_test_bot"
    data = client.get("/api/v1/notifications/news").json()["data"]
    assert data["bot_url"] == "https://t.me/nz_test_bot?start=news" and data["gift_coins"] >= 0
