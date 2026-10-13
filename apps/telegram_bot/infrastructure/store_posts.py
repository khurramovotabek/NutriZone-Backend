"""
Branch owners' own feeds (beat task telegram_bot.store_posts, every 30 s):

  Orders bot     a rich post for every till sale at their branch and every online order assigned to it, then a short
                 status update (confirmed / on the way / delivered / cancelled …) as a reply to that post
  Analytics bot  an alert for every customer message in their store's chats that is still unanswered after the
                 support desk's alert delay (ChatSettings.alert_after_minutes)

Only to people who pressed /start (staff_access.subscribers), only for their own branches, only what happened after
they started, exactly once (TelegramStorePost unique row claimed before sending; released again if Telegram fails,
so the next run retries; a blocked bot deactivates the subscriber).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.telegram_bot.infrastructure import rich as R
from apps.telegram_bot.infrastructure import staff_access

logger = logging.getLogger("nutrizone.telegram_bot.store_posts")
LOOKBACK = timedelta(days=1)
UPDATE_STATUSES = ("confirmed", "processing", "shipped", "delivered", "completed", "cancelled", "returned", "failed")


def _claim(bot: str, key: str, chat_id) -> object | None:
    from apps.telegram_bot.infrastructure.models import TelegramStorePost

    try:
        with transaction.atomic():  # a savepoint: an already-claimed key must not poison the surrounding transaction
            return TelegramStorePost.objects.create(bot=bot, key=key, chat_id=chat_id)
    except IntegrityError:
        return None


def _deliver(bot: str, token: str, sub, key: str, build, reply_to_key: str | None = None) -> bool:
    """Claim → build → send; False when it was already done or failed (then released for a retry)."""
    from apps.telegram_bot.infrastructure.models import TelegramStorePost

    claim = _claim(bot, key, sub.chat_id)
    if claim is None:
        return False
    try:
        doc, keyboard = build()
        if doc is None:
            return True  # nothing to send (e.g. the sale vanished) -- keep the claim so it isn't retried forever
        message_id = R.send(token, sub.chat_id, doc, keyboard)
        claim.message_id = message_id
        claim.save(update_fields=["message_id"])
        return True
    except R.RichSendError as exc:
        TelegramStorePost.objects.filter(pk=claim.pk).delete()
        if R.is_blocked(exc):
            staff_access.deactivate(bot, sub.chat_id)
        logger.warning("store post %s to %s failed: %s", key, sub.chat_id, exc)
    except Exception:  # noqa: BLE001
        TelegramStorePost.objects.filter(pk=claim.pk).delete()
        logger.exception("store post %s to %s failed", key, sub.chat_id)
    return False


def _owner_subscribers(bot: str):
    """(subscriber, scope) for every active subscriber who owns at least one branch, skipping the staff channel chat."""
    channel = str(getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", "") or "") if bot == "orders" else ""
    for sub in staff_access.subscribers(bot):
        if bot == "orders" and str(sub.chat_id) == channel:
            continue  # that chat already gets every post from the Orders channel feed
        stores, name = staff_access.owned_stores(sub.telegram_user_id or sub.chat_id)
        if stores:
            yield sub, stores


# ---------------------------------------------------------------- Orders bot


def orders_feed() -> dict:
    from apps.ordering.infrastructure.models import OrderModel
    from apps.pos.infrastructure.models import SaleModel
    from apps.telegram_bot.infrastructure import orders_bot, orders_rich

    token = orders_bot.token()
    if not token:
        return {"skipped": "no token"}
    sent = updates = 0
    for sub, stores in _owner_subscribers("orders"):
        ids = [s.id for s in stores]
        since = max(sub.started_at, timezone.now() - LOOKBACK)
        for sale_id in SaleModel.objects.filter(branch_id__in=ids, channel="store", status__in=("completed", "refunded"), completed_at__gte=since).order_by("completed_at").values_list("id", flat=True)[:30]:
            sent += _deliver("orders", token, sub, f"sale:{sale_id}", lambda sid=sale_id: orders_rich.sale_doc(sid))
        for order in OrderModel.objects.filter(fulfilment_store_id__in=ids).exclude(status="draft").filter(placed_at__gte=since).order_by("placed_at").values("id", "status")[:30]:
            oid = order["id"]
            if _deliver("orders", token, sub, f"order:{oid}", lambda o=oid: _order_post(o)):
                sent += 1
                continue
            if order["status"] in UPDATE_STATUSES:
                updates += _deliver("orders", token, sub, f"order:{oid}:{order['status']}", lambda o=oid, st=order["status"]: _status_update(o, st))
    return {"sent": sent, "updates": updates}


def _order_post(order_id):
    from apps.telegram_bot.infrastructure import orders_rich

    doc, meta = orders_rich.order_doc(order_id)
    if doc is None:
        return None, None
    return doc, _owner_order_keyboard(meta)


def _owner_order_keyboard(meta) -> list:
    rows = []
    if meta["has_point"]:
        a = meta["address"]
        la, ln = f"{a.latitude:.6f}", f"{a.longitude:.6f}"
        rows.append([{"text": "🧭 Yandex yo'nalish", "url": f"https://yandex.uz/maps/?rtext=~{la},{ln}&rtt=auto"}, {"text": "Google", "url": f"https://www.google.com/maps/search/?api=1&query={la},{ln}"}])
    rows.append([{"text": "📋 Bugungi ro'yxat", "callback_data": "ob:today"}])
    return rows


def _status_update(order_id, status):
    from apps.ordering.infrastructure.models import OrderModel
    from apps.telegram_bot.infrastructure.orders_rich import STATUS

    o = OrderModel.objects.filter(id=order_id).values("order_number", "shipping_recipient_name").first()
    if o is None:
        return None, None
    icon, label = STATUS.get(status, ("•", status))
    doc = R.RichDoc()
    doc.add(R.p(f"{icon} {R.b(o['order_number'])} — <b>{R.e(label)}</b>"),
            R.p(f"👤 {R.e(o['shipping_recipient_name'] or 'Mijoz')} · {R.time_tag(timezone.now(), 't', timezone.localtime(timezone.now()).strftime('%H:%M'))}"))
    doc.fallback = f"{icon} <b>{R.e(o['order_number'])}</b> — {R.e(label)}"
    return doc, []


# ---------------------------------------------------------------- Analytics bot: unanswered store chats


def store_chats_feed() -> dict:
    from apps.chat.infrastructure.automation import chat_settings
    from apps.chat.infrastructure.models import ConversationModel, MessageModel, ParticipantModel
    from apps.telegram_bot.infrastructure import analytics_bot

    token = analytics_bot.token()
    if not token:
        return {"skipped": "no token"}
    delay = timedelta(minutes=max(chat_settings().alert_after_minutes, 1))
    sent = 0
    for sub, stores in _owner_subscribers("analytics"):
        names = {s.id: s.name for s in stores}
        convs = list(ConversationModel.objects.filter(conversation_type="customer_sales", status="open", store_id__in=list(names)).values_list("id", "store_id"))
        if not convs:
            continue
        store_of = dict(convs)
        customers = dict(ParticipantModel.objects.filter(conversation_id__in=list(store_of), role="customer").values_list("conversation_id", "user_id"))
        latest = MessageModel.objects.filter(conversation_id__in=list(store_of)).order_by("conversation_id", "-created_at").distinct("conversation_id")
        for m in latest:
            if customers.get(m.conversation_id) != m.sender_id or m.created_at > timezone.now() - delay or m.created_at < sub.started_at:
                continue
            sent += _deliver("analytics", token, sub, f"chat:{m.pk}", lambda msg=m, sid=store_of[m.conversation_id]: _chat_alert(msg, names.get(sid, "Filial")))
    return {"sent": sent}


def _chat_alert(message, store_name: str):
    from apps.identity.infrastructure.models import User
    from apps.platform.infrastructure.business_analytics import duration
    from apps.telegram_bot.infrastructure.analytics_bot import customer_label, preview

    u = User.objects.filter(id=message.sender_id).first()
    minutes = int((timezone.now() - message.created_at).total_seconds() // 60)
    frontend = (getattr(settings, "FRONTEND_URL", None) or "").rstrip("/")
    doc = R.RichDoc()
    doc.add(R.h(3, f"💬 Javobsiz chat · {R.e(store_name)}"),
            R.table([], [[R.e("👤 Mijoz"), R.b(customer_label(u))], [R.e("⏱ Kutmoqda"), R.b(duration(minutes))],
                         [R.e("🕒 Yozgan"), R.time_tag(message.created_at, "t", timezone.localtime(message.created_at).strftime("%H:%M"))]], align=["left", "left"]),
            R.quote(R.e(preview(message))))
    keyboard = [[{"text": "💬 Javob berish", "url": f"{frontend}/profile/store/inquiries"}]] if frontend.startswith("https://") else []
    doc.fallback = f"💬 <b>Javobsiz chat · {R.e(store_name)}</b>\n👤 {R.e(customer_label(u))} · {duration(minutes)}\n«{R.e(preview(message))}»"
    return doc, keyboard


def run() -> dict:
    out = {}
    for name, fn in (("orders", orders_feed), ("chats", store_chats_feed)):
        try:
            out[name] = fn()
        except Exception:  # noqa: BLE001 - one feed failing never stops the other
            logger.exception("store posts: %s feed failed", name)
            out[name] = "error"
    return out
