"""
Loyalty → Telegram notifications (coins earned, tier upgrade, referral bonus,
coins expiring soon), in the customer's own language.

`queue()` is called from reward code paths; it defers the actual send until
the surrounding transaction commits (a rolled-back reward never notifies) and
hands it to Celery so a slow/unavailable Telegram API never blocks an order
save. Sending is best effort: a customer without a linked Telegram account,
or programme settings with notifications off, simply gets nothing.
"""
from __future__ import annotations

import logging
import uuid

from django.conf import settings
from django.db import transaction

logger = logging.getLogger("nutrizone.app")

TIER_EMOJI = {"bronze": "🥉", "silver": "🥈", "gold": "🥇", "platinum": "💠", "diamond": "💎", "elite": "🛡", "legend": "🔥", "vip": "👑"}

TEXT = {
    "uz": {
        "earned_pos": "🪙 <b>+{coins} coin</b> hisobingizga tushdi!\n\n🛍 Do'kondagi xarid <b>{order}</b> · {tier} {percent}%\n💰 Balans: <b>{balance} coin</b>",
        "earned": "🪙 <b>+{coins} coin</b> hisobingizga tushdi!\n\n📦 Buyurtma <b>#{order}</b> yetkazildi · {tier} {percent}%\n💰 Balans: <b>{balance} coin</b>",
        "tier_up": "🎉 <b>Tabriklaymiz!</b>\n\nSiz {emoji} <b>{tier}</b> tarifiga o'tdingiz — endi har bir xariddan <b>{percent}%</b> coin qaytadi.",
        "referral_referrer": "🤝 <b>+{coins} coin!</b>\n\nSiz taklif qilgan do'stingiz birinchi xaridini amalga oshirdi. Rahmat!\n💰 Balans: <b>{balance} coin</b>",
        "referral_referee": "🎁 <b>Xush kelibsiz bonusi: +{coins} coin!</b>\n\nDo'stingiz taklifi bilan qilgan birinchi xaridingiz uchun.\n💰 Balans: <b>{balance} coin</b>",
        "expiring": "⏳ <b>{coins} coin</b> {date} kuni kuyadi.\n\nUlarni keyingi xaridingizda ishlating — buyurtmaning {percent}% gacha qismini coin bilan to'lashingiz mumkin.",
        "btn_wallet": "🪙 Bonuslarim",
        "btn_site": "🌐 Saytda ochish",
    },
    "ru": {
        "earned_pos": "🪙 <b>+{coins} коинов</b> зачислено!\n\n🛍 Покупка в магазине <b>{order}</b> · {tier} {percent}%\n💰 Баланс: <b>{balance} коинов</b>",
        "earned": "🪙 <b>+{coins} коинов</b> зачислено!\n\n📦 Заказ <b>#{order}</b> доставлен · {tier} {percent}%\n💰 Баланс: <b>{balance} коинов</b>",
        "tier_up": "🎉 <b>Поздравляем!</b>\n\nВы перешли на уровень {emoji} <b>{tier}</b> — теперь с каждой покупки возвращается <b>{percent}%</b> коинами.",
        "referral_referrer": "🤝 <b>+{coins} коинов!</b>\n\nПриглашённый вами друг совершил первую покупку. Спасибо!\n💰 Баланс: <b>{balance} коинов</b>",
        "referral_referee": "🎁 <b>Приветственный бонус: +{coins} коинов!</b>\n\nЗа первую покупку по приглашению друга.\n💰 Баланс: <b>{balance} коинов</b>",
        "expiring": "⏳ <b>{coins} коинов</b> сгорят {date}.\n\nИспользуйте их в следующей покупке — коинами можно оплатить до {percent}% заказа.",
        "btn_wallet": "🪙 Мои бонусы",
        "btn_site": "🌐 Открыть на сайте",
    },
    "en": {
        "earned_pos": "🪙 <b>+{coins} coins</b> credited!\n\n🛍 In-store purchase <b>{order}</b> · {tier} {percent}%\n💰 Balance: <b>{balance} coins</b>",
        "earned": "🪙 <b>+{coins} coins</b> credited!\n\n📦 Order <b>#{order}</b> delivered · {tier} {percent}%\n💰 Balance: <b>{balance} coins</b>",
        "tier_up": "🎉 <b>Congratulations!</b>\n\nYou've reached {emoji} <b>{tier}</b> — you now get <b>{percent}%</b> back in coins on every purchase.",
        "referral_referrer": "🤝 <b>+{coins} coins!</b>\n\nThe friend you invited just completed their first order. Thank you!\n💰 Balance: <b>{balance} coins</b>",
        "referral_referee": "🎁 <b>Welcome bonus: +{coins} coins!</b>\n\nFor your first order via a friend's invite.\n💰 Balance: <b>{balance} coins</b>",
        "expiring": "⏳ <b>{coins} coins</b> expire on {date}.\n\nUse them on your next order — coins can cover up to {percent}% of it.",
        "btn_wallet": "🪙 My rewards",
        "btn_site": "🌐 Open on the website",
    },
}


def fmt(n) -> str:
    return f"{int(n):,}".replace(",", " ")


def queue(kind: str, user_id: uuid.UUID, **payload) -> None:
    from apps.loyalty.infrastructure.tasks import send_loyalty_notification

    try:
        to_inbox(kind, user_id, payload)
    except Exception:  # noqa: BLE001 - the inbox copy is best effort, like the Telegram one
        logger.exception("loyalty: inbox notification %s for %s failed", kind, user_id)
    if kind in INBOX_ONLY:
        return

    def _dispatch() -> None:
        try:
            send_loyalty_notification.delay(kind, str(user_id), payload)
        except Exception:  # noqa: BLE001 - broker down: fall back to sending inline, still best effort
            try:
                send(kind, user_id, payload)
            except Exception:  # noqa: BLE001
                logger.exception("loyalty: notification %s for %s failed", kind, user_id)

    transaction.on_commit(_dispatch)


# Kinds with no Loyalty-specific Telegram text: the inbox sends the Telegram copy itself.
INBOX_ONLY = {"granted", "deducted", "tier_set", "tier_risk"}


def to_inbox(kind: str, user_id, payload: dict) -> None:
    """Mirrors every loyalty event into the customer's in-app inbox (apps.notifications.infrastructure.notify)."""
    from apps.loyalty.infrastructure.models import LoyaltyTier, Wallet, WalletTransaction
    from apps.notifications.infrastructure.notify import notify

    def balance() -> str:
        return fmt(Wallet.objects.filter(user_id=user_id).values_list("balance", flat=True).first() or 0)

    def pct(value) -> str:
        return f"{value.normalize():f}" if value is not None else ""

    link = "/account/loyalty"
    if kind == "earned":
        tx = WalletTransaction.objects.filter(id=payload.get("tx_id")).first()
        if tx is None:
            return
        notify(user_id, "coins_earned_pos" if tx.note == "POS purchase" else "coins_earned",
               {"coins": fmt(tx.amount), "order": tx.order_number or "—", "percent": pct(tx.tier_percent), "balance": balance()},
               link=link, dedupe_key=f"coins:{tx.id}", telegram=False)
    elif kind in ("tier_up", "tier_set"):
        tier = LoyaltyTier.objects.filter(slug=payload.get("tier_slug")).first()
        if tier is None:
            return
        notify(user_id, "tier_up" if kind == "tier_up" else "tier_changed", {"tier": tier.name, "percent": pct(tier.percent)},
               link=link, dedupe_key=f"{kind}:{user_id}:{tier.slug}:{payload.get('ref', '')}", telegram=kind == "tier_set")
    elif kind == "referral":
        tx = WalletTransaction.objects.filter(id=payload.get("tx_id")).select_related("referral", "wallet").first()
        if tx is None or tx.referral is None:
            return
        referee = tx.referral.referee_id == tx.wallet.user_id
        notify(user_id, "welcome_bonus" if referee else "referral_bonus", {"coins": fmt(tx.amount), "balance": balance()},
               link=link, dedupe_key=f"coins:{tx.id}", telegram=False)
    elif kind == "expiring":
        notify(user_id, "coins_expiring", {"coins": fmt(payload["coins"]), "date": payload["date"]},
               link=link, dedupe_key=f"expiring:{user_id}:{payload['date']}", telegram=False)
    elif kind == "tier_risk":
        notify(user_id, "tier_at_risk",
               {"tier": payload["tier"], "lower": payload["lower"], "amount": fmt(payload["needed"]), "date": payload["date"], "percent": payload["percent"]},
               link=link, dedupe_key=f"tier_risk:{user_id}:{payload['tier_slug']}:{payload['date']}")
    elif kind in ("granted", "deducted"):
        tx = WalletTransaction.objects.filter(id=payload.get("tx_id")).first()
        if tx is None:
            return
        note = (tx.note or "").strip()
        notify(user_id, "coins_granted" if kind == "granted" else "coins_deducted",
               {"coins": fmt(abs(tx.amount)), "balance": balance(), "note": f"{note}. " if note else ""},
               link=link, dedupe_key=f"coins:{tx.id}")


def keyboard(lang: str) -> list:
    rows = [[{"text": TEXT[lang]["btn_wallet"], "callback_data": "menu:loyalty"}]]
    base = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    if base.startswith("https://"):  # Telegram only accepts https URL buttons
        rows.append([{"text": TEXT[lang]["btn_site"], "url": f"{base}/account/loyalty"}])
    return rows


def send(kind: str, user_id: uuid.UUID | str, payload: dict) -> bool:
    """Renders and sends one notification. Returns False when it was (legitimately) skipped."""
    from apps.identity.infrastructure.models import User
    from apps.loyalty.infrastructure.models import LoyaltySettings, LoyaltyTier, Wallet, WalletTransaction

    cfg = LoyaltySettings.load()
    if not cfg.telegram_notifications:
        return False
    user = User.objects.filter(id=user_id).only("telegram_user_id", "language").first()
    if user is None or not user.telegram_user_id:
        return False
    lang = user.language if user.language in TEXT else "uz"
    T = TEXT[lang]
    balance = fmt(Wallet.objects.filter(user_id=user_id).values_list("balance", flat=True).first() or 0)

    if kind == "earned":
        tx = WalletTransaction.objects.filter(id=payload.get("tx_id")).first()
        if tx is None:
            return False
        key = "earned_pos" if tx.note == "POS purchase" else "earned"
        text = T[key].format(coins=fmt(tx.amount), order=tx.order_number or "—", tier=tx.tier_name, percent=f"{tx.tier_percent.normalize():f}" if tx.tier_percent else "", balance=balance)
    elif kind == "tier_up":
        tier = LoyaltyTier.objects.filter(slug=payload.get("tier_slug")).first()
        if tier is None:
            return False
        text = T["tier_up"].format(emoji=TIER_EMOJI.get(tier.icon, "⭐"), tier=tier.name, percent=f"{tier.percent.normalize():f}")
    elif kind == "referral":
        tx = WalletTransaction.objects.filter(id=payload.get("tx_id")).select_related("referral").first()
        if tx is None or tx.referral is None:
            return False
        key = "referral_referee" if tx.referral.referee_id == tx.wallet.user_id else "referral_referrer"
        text = T[key].format(coins=fmt(tx.amount), balance=balance)
    elif kind == "expiring":
        text = T["expiring"].format(coins=fmt(payload["coins"]), date=payload["date"], percent=cfg.max_redeem_percent)
    else:
        return False

    from apps.notifications.infrastructure import composition as notifications_composition

    notifications_composition.build_telegram_gateway().send_message_with_keyboard(str(user.telegram_user_id), text, keyboard(lang))
    return True
