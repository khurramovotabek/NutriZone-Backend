"""
News & promotions subscription (Telegram bot) and its one-time welcome gift.

* subscribe / unsubscribe -- from the bot menu ("📰 Yangiliklar va aksiyalar") or the site's deep link
  t.me/<bot>?start=news. Re-subscribing keeps the original record (the gift is never paid twice).
* the gift -- LoyaltySettings.subscribe_gift_coins, credited once, on the customer's first completed purchase
  after subscribing (an online order when it is fulfilled, or a branch kassa sale with the customer attached).
* broadcasts can target audience="subscribers".
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("nutrizone.app")


def gift_coins() -> int:
    from apps.loyalty.infrastructure.services import programme

    return int(programme().subscribe_gift_coins or 0)


def bot_url(payload: str = "news") -> str | None:
    username = (getattr(settings, "TELEGRAM_BOT_USERNAME", None) or "").lstrip("@")
    return f"https://t.me/{username}?start={payload}" if username else None


def is_subscribed(user_id) -> bool:
    from apps.notifications.infrastructure.models import NewsSubscription

    return NewsSubscription.objects.filter(user_id=user_id, is_active=True).exists()


def subscribe(user_id, source: str = "bot") -> tuple[object, bool]:
    """(subscription, newly_subscribed). Tells the customer (inbox + Telegram) when it is a new subscription."""
    from apps.notifications.infrastructure.models import NewsSubscription

    sub, created = NewsSubscription.objects.get_or_create(user_id=user_id, defaults={"source": source[:32]})
    fresh = created
    if not created and not sub.is_active:
        sub.is_active, sub.unsubscribed_at, sub.subscribed_at = True, None, timezone.now()
        sub.save(update_fields=["is_active", "unsubscribed_at", "subscribed_at"])
        fresh = True
    if fresh:
        from apps.notifications.infrastructure.notify import notify

        coins = gift_coins() if not sub.gift_granted_at else 0
        # inbox only: the bot answers in the chat itself
        notify(user_id, "news_subscribed", {"gift": _gift_line(coins)}, link="/loyalty", dedupe_key=f"news_subscribed:{sub.id}:{sub.subscribed_at:%Y%m%d%H%M}", telegram=False)
    return sub, fresh


def _gift_line(coins: int) -> str:
    return f" 🎁 +{coins:,} coin".replace(",", " ") if coins > 0 else ""


def unsubscribe(user_id) -> bool:
    from apps.notifications.infrastructure.models import NewsSubscription

    return bool(NewsSubscription.objects.filter(user_id=user_id, is_active=True).update(is_active=False, unsubscribed_at=timezone.now()))


def on_purchase(user_id, purchase_id, number: str, purchased_at=None) -> int:
    """Pays the welcome gift on the first purchase after subscribing. Returns the coins credited (0 if none)."""
    if not user_id:
        return 0
    from apps.loyalty.infrastructure.models import WalletTransactionKind
    from apps.loyalty.infrastructure.services import _credit
    from apps.notifications.infrastructure.models import NewsSubscription

    coins = gift_coins()
    if coins <= 0:
        return 0
    when = purchased_at or timezone.now()
    with transaction.atomic():
        sub = NewsSubscription.objects.select_for_update().filter(user_id=user_id, is_active=True, gift_granted_at__isnull=True).first()
        if sub is None or sub.subscribed_at > when:
            return 0
        tx = _credit(user_id, coins, WalletTransactionKind.ADJUSTMENT, note=f"Telegram obuna sovg'asi · {number}"[:255])
        if tx is None:
            return 0
        sub.gift_coins, sub.gift_granted_at, sub.gift_purchase = coins, timezone.now(), str(number)[:40]
        sub.save(update_fields=["gift_coins", "gift_granted_at", "gift_purchase"])
    from apps.notifications.infrastructure.notify import notify

    notify(user_id, "subscription_gift", {"coins": f"{coins:,}".replace(",", " "), "number": number}, link="/loyalty", dedupe_key=f"subscription_gift:{sub.id}")
    return coins


def safe_on_purchase(*args, **kwargs) -> int:
    """Never lets the gift break a sale / an order's cashback."""
    try:
        return on_purchase(*args, **kwargs)
    except Exception:  # noqa: BLE001
        logger.exception("subscription gift failed for %s", args[:1])
        return 0


def public_info() -> dict:
    from apps.notifications.infrastructure.models import NewsSubscription

    return {"gift_coins": gift_coins(), "bot_url": bot_url(), "subscribers": NewsSubscription.objects.filter(is_active=True).count()}
