"""
Support-desk automation around the chat (settings in `ChatSettings`, dashboard → Chat → Chat sozlamalari):

* working hours        -- `is_open(now)`: the desk's hours and days, Tashkent time.
* out-of-hours reply   -- a customer writing to Support outside working hours gets one SYSTEM message ("we'll reply
                          from 9:00"), at most once per conversation per 12 hours; sent through SendMessage after the
                          customer's message commits.
* unanswered alert     -- `alert_waiting()` (Celery beat, every 2 minutes) posts each support chat whose customer has
                          waited longer than N minutes to the staff Telegram channel, once per waiting message.
* rating request       -- when a support chat is closed, the customer is asked (bell + Telegram) to rate it 1–5 ★;
                          the score is stored in `ConversationRating`.
* order bot            -- "Buyurtmam qayerda?" / "где мой заказ" / an order number → the bot answers at once (any hour)
                          with the customer's order card(s); the operator still sees the chat as waiting.
* low rating           -- a 1–2 ★ score puts the chat under review ("nazoratda") and alerts the manager on Telegram.
* closings             -- every closing is recorded (`ConversationClosing`) for the operator report.
* quick-reply variables -- `render_template()` fills {ism}, {buyurtma_raqami}, {yetkazish_sanasi}, ... per chat.
* cards                -- `card_payload()` resolves a CARD message ("product:<uuid>" / "order:<uuid>") into what the
                          two sides see: name, photo, price / status, link.

Every automatic action is recorded in `ChatAutomationLog` (unique kind + ref) so nothing is sent twice.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger("nutrizone.app")
TZ = ZoneInfo("Asia/Tashkent")
BOT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "nutrizone-support-bot")  # the sender of automatic messages
AUTO_REPLY_GAP = timedelta(hours=12)
DAY_NAMES = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]


def chat_settings():
    from apps.chat.infrastructure.models import ChatSettings

    return ChatSettings.load()


def is_open(now: datetime | None = None, cfg=None) -> bool:
    cfg = cfg or chat_settings()
    local = timezone.localtime(now or timezone.now(), TZ)
    if local.weekday() not in (cfg.work_days or []):
        return False
    start, end = cfg.work_start, cfg.work_end
    t = local.time()
    return start <= t < end if start <= end else (t >= start or t < end)  # an overnight shift (e.g. 20:00–02:00)


def hours_label(cfg=None) -> str:
    cfg = cfg or chat_settings()
    days = sorted(cfg.work_days or [])
    span = f"{DAY_NAMES[days[0]]}–{DAY_NAMES[days[-1]]}" if days and days == list(range(days[0], days[-1] + 1)) else ", ".join(DAY_NAMES[d] for d in days)
    return f"{span} {cfg.work_start:%H:%M}–{cfg.work_end:%H:%M}" if days else "ish kunlari belgilanmagan"


def staff_names() -> dict:
    """Chat-domain staff id (uuid5 of the admin pk, see chat_view.staff_uuid) → display name."""
    from django.contrib.auth import get_user_model

    return {uuid.uuid5(uuid.NAMESPACE_DNS, f"nutrizone-admin-staff-{u.pk}"): (u.get_full_name() or u.get_username()) for u in get_user_model().objects.filter(is_staff=True)}


def _base_url() -> str:
    return (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")


def _desk_button(conversation_id, text: str = "Javob berish →") -> list:
    base = _base_url()
    return [[{"text": text, "url": f"{base}/django-admin/chat/?c={conversation_id}"}]] if base.startswith("https://") else []


def _log(kind: str, ref: str, conversation_id) -> bool:
    """True when this action is new (and now recorded); False when it was already done."""
    from apps.chat.infrastructure.models import ChatAutomationLog

    try:
        with transaction.atomic():
            ChatAutomationLog.objects.create(kind=kind, ref=ref[:80], conversation_id=conversation_id)
        return True
    except IntegrityError:
        return False


# ---------------------------------------------------------------- out-of-hours auto-reply


def _customer_language(user_id) -> str:
    from apps.identity.infrastructure.models import User

    return (User.objects.filter(id=user_id).values_list("language", flat=True).first() or "uz") if user_id else "uz"


def maybe_auto_reply(message_id) -> bool:
    """A customer's message to Support outside working hours → one SYSTEM reply per conversation per 12 h."""
    from apps.chat.domain.enums import MessageType
    from apps.chat.infrastructure import composition
    from apps.chat.infrastructure.models import (
        ChatAutomationLog,
        ConversationModel,
        MessageModel,
        ParticipantModel,
    )
    from apps.chat.infrastructure.realtime import message_payload, push_message

    message = MessageModel.objects.filter(pk=message_id).first()
    if message is None or message.message_type == "system":
        return False
    conv = ConversationModel.objects.filter(pk=message.conversation_id, status="open", conversation_type="customer_support").first()
    if conv is None or not ParticipantModel.objects.filter(conversation_id=conv.id, user_id=message.sender_id, role="customer").exists():
        return False
    cfg = chat_settings()
    if not cfg.auto_reply_enabled or is_open(message.created_at, cfg):
        return False
    if ChatAutomationLog.objects.filter(kind="auto_reply", conversation_id=conv.id, created_at__gte=timezone.now() - AUTO_REPLY_GAP).exists():
        return False
    texts = cfg.auto_reply_text or {}
    text = texts.get(_customer_language(message.sender_id)) or texts.get("uz") or next(iter(texts.values()), "")
    if not text.strip() or not _log("auto_reply", f"{conv.id}:{message.id}", conv.id):
        return False
    text = f"{text.strip()}\n🕘 {hours_label(cfg)}"
    reply = composition.build_send_message(BOT_ID).execute(conversation_id=conv.id, sender_id=BOT_ID, message_type=MessageType.SYSTEM, content=text)
    push_message(conv.id, message_payload(reply), BOT_ID, ParticipantModel.objects.filter(conversation_id=conv.id, removed_at__isnull=True).values_list("user_id", flat=True))
    return True


@receiver(post_save, sender="chat.MessageModel", dispatch_uid="chat.auto_reply")
def _on_message(sender, instance, created: bool, **kwargs) -> None:
    if not created or instance.message_type == "system" or instance.sender_id == BOT_ID:
        return

    def run():
        for step in (maybe_order_bot, maybe_auto_reply):  # the order answer first, then (out of hours) when a human will reply
            try:
                step(instance.pk)
            except Exception:  # noqa: BLE001 - automation never breaks the customer's own message
                logger.exception("chat: %s failed for message %s", step.__name__, instance.pk)

    transaction.on_commit(run)


# ---------------------------------------------------------------- rating request on close


@receiver(pre_save, sender="chat.ConversationModel", dispatch_uid="chat.rating_prev_status")
def _remember_status(sender, instance, **kwargs) -> None:
    if instance.pk:
        instance._nz_prev_status = sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()


@receiver(post_save, sender="chat.ConversationModel", dispatch_uid="chat.rating_request")
def _on_conversation(sender, instance, created: bool, **kwargs) -> None:
    if created or instance.status != "closed" or getattr(instance, "_nz_prev_status", None) == "closed":
        return
    conversation_id = instance.pk
    if instance.conversation_type != "customer_sales":
        from apps.chat.infrastructure.models import ConversationClosing

        ConversationClosing.objects.create(conversation_id=conversation_id, operator_id=instance.assigned_operator_id, closed_at=timezone.now())
    transaction.on_commit(lambda: _ask_rating(conversation_id))


def _ask_rating(conversation_id) -> None:
    try:
        ask_rating(conversation_id)
    except Exception:  # noqa: BLE001
        logger.exception("chat: rating request failed for %s", conversation_id)


def _last_rating_request(conversation_id):
    from apps.chat.infrastructure.models import ChatAutomationLog

    return ChatAutomationLog.objects.filter(kind="rating_request", conversation_id=conversation_id).order_by("-created_at").values_list("created_at", flat=True).first()


def can_rate(conversation_id, status: str) -> bool:
    """A closed support chat whose latest closing asked for a rating that hasn't been given yet."""
    from apps.chat.infrastructure.models import ConversationRating

    asked = _last_rating_request(conversation_id)
    return status != "open" and asked is not None and not ConversationRating.objects.filter(conversation_id=conversation_id, created_at__gte=asked).exists()


def ask_rating(conversation_id) -> bool:
    """On closing: ask the customer to rate -- when staff answered something since the previous request (one request per closing)."""
    from apps.chat.infrastructure.models import ConversationModel, MessageModel, ParticipantModel
    from apps.notifications.infrastructure.notify import notify

    conv = ConversationModel.objects.filter(pk=conversation_id, conversation_type="customer_support").first()
    if conv is None or not chat_settings().rating_enabled:
        return False
    customer_id = ParticipantModel.objects.filter(conversation_id=conv.id, role="customer").values_list("user_id", flat=True).first()
    staff = MessageModel.objects.filter(conversation_id=conv.id).exclude(sender_id=customer_id).exclude(sender_id=BOT_ID).exclude(message_type="system")
    previous = _last_rating_request(conv.id)
    if previous is not None:
        staff = staff.filter(created_at__gt=previous)
    from apps.chat.infrastructure.models import ChatAutomationLog

    closing = ChatAutomationLog.objects.filter(kind="rating_request", conversation_id=conv.id).count() + 1  # the n-th rated closing
    if customer_id is None or not staff.exists() or not _log("rating_request", f"{conv.id}:{closing}", conv.id):
        return False
    notify(customer_id, "chat_rating", {}, link=f"/account/chat?conversation={conv.id}", dedupe_key=f"chat_rating:{conv.id}:{closing}")
    return True


def rate(conversation_id, customer_id, score: int, comment: str = ""):
    """The customer's score for the latest closing of a support chat -- once per closing, 1..5, only by its own customer."""
    from apps.chat.infrastructure.models import ConversationModel, ConversationRating, ParticipantModel
    from common.exceptions import ConflictError, ResourceNotFound, ValidationFailed

    conv = ConversationModel.objects.filter(pk=conversation_id).first()
    if conv is None or not ParticipantModel.objects.filter(conversation_id=conversation_id, user_id=customer_id, role="customer").exists():
        raise ResourceNotFound("Conversation not found.")
    if not isinstance(score, int) or not 1 <= score <= 5:
        raise ValidationFailed("Score must be 1–5.", details={"fields": [{"field": "score", "code": "OUT_OF_RANGE"}]})
    with transaction.atomic():
        ConversationModel.objects.select_for_update().filter(pk=conversation_id).first()  # one rating per closing, even on a double click
        if not can_rate(conversation_id, conv.status):
            raise ConflictError("This conversation can't be rated right now (it is open or was already rated).")
        rating = ConversationRating.objects.create(conversation=conv, customer_id=customer_id, operator_id=conv.assigned_operator_id, score=score,
                                                   comment=(comment or "").strip()[:500], review_status="open" if score <= LOW_SCORE else "")
    if rating.review_status == "open":
        transaction.on_commit(lambda: _safe(alert_low_rating, rating.pk))
    return rating


# ---------------------------------------------------------------- low rating → under review + manager alert

LOW_SCORE = 2


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001
        logger.exception("chat: %s failed", fn.__name__)
        return None


def alert_low_rating(rating_id) -> bool:
    """A 1–2 ★ rating → the staff Telegram channel: who, which operator, the comment, a button to the chat (once per rating)."""
    from html import escape

    from apps.chat.infrastructure.models import ConversationRating
    from apps.identity.infrastructure.models import User

    rating = ConversationRating.objects.filter(pk=rating_id).first()
    chat = getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", None)
    if rating is None or not chat or not chat_settings().low_rating_alert or not _log("low_rating", str(rating.pk), rating.conversation_id):
        return False
    u = User.objects.filter(id=rating.customer_id).first()
    who = f"{u.full_name or 'Mijoz'} ({u.phone_number})" if u else "Mijoz"
    operator = staff_names().get(rating.operator_id, "biriktirilmagan") if rating.operator_id else "biriktirilmagan"
    lines = [f"⚠️ <b>Past baho: {'★' * rating.score}{'☆' * (5 - rating.score)} ({rating.score}/5)</b>", f"👤 {escape(who)}", f"🎧 Operator: {escape(operator)}"]
    if rating.comment:
        lines.append(f"💬 «{escape(rating.comment[:300])}»")
    lines.append("Suhbat nazoratga olindi — mijoz bilan bog'lanib, natijani dashboardda belgilang.")
    from apps.notifications.infrastructure import composition

    composition.build_orders_telegram_gateway().send_message_with_keyboard(str(chat), "\n".join(lines), _desk_button(rating.conversation_id, "Suhbatni ochish →"))
    return True


def resolve_review(conversation_id, by: str, note: str = "") -> int:
    """A manager closes the review of a chat's low ratings ("Hal qilindi") -- returns how many were open."""
    from apps.chat.infrastructure.models import ConversationRating

    return ConversationRating.objects.filter(conversation_id=conversation_id, review_status="open").update(
        review_status="resolved", reviewed_by=(by or "")[:150], reviewed_at=timezone.now(), review_note=(note or "").strip()[:500])


def under_review(conversation_ids) -> dict:
    """conversation id → its open low rating {score, comment} for the chats that are "nazoratda"."""
    from apps.chat.infrastructure.models import ConversationRating

    rows = ConversationRating.objects.filter(conversation_id__in=list(conversation_ids), review_status="open").order_by("conversation_id", "-created_at").distinct("conversation_id")
    return {r.conversation_id: {"score": r.score, "comment": r.comment, "at": r.created_at.isoformat()} for r in rows}


# ---------------------------------------------------------------- staff alert for unanswered chats


def waiting_conversations(older_than: timedelta) -> list[dict]:
    """Open support chats whose latest message is the customer's and older than `older_than`."""
    from apps.chat.infrastructure.models import ConversationModel, MessageModel, ParticipantModel

    ids = list(ConversationModel.objects.filter(status="open", conversation_type="customer_support").values_list("id", flat=True))
    customers = dict(ParticipantModel.objects.filter(conversation_id__in=ids, role="customer").values_list("conversation_id", "user_id"))
    cutoff = timezone.now() - older_than
    out = []
    for m in MessageModel.objects.filter(conversation_id__in=ids).exclude(sender_id=BOT_ID).order_by("conversation_id", "-created_at").distinct("conversation_id"):
        if customers.get(m.conversation_id) == m.sender_id and m.created_at <= cutoff:  # a bot answer doesn't count as answered
            out.append({"conversation_id": m.conversation_id, "message": m, "customer_id": m.sender_id})
    return out


def _alert_text(item) -> str:
    from html import escape

    from apps.identity.infrastructure.models import User

    u = User.objects.filter(id=item["customer_id"]).first()
    m = item["message"]
    minutes = int((timezone.now() - m.created_at).total_seconds() // 60)
    preview = (m.content or {"attachment": "📷 rasm", "sticker": "stiker"}.get(m.message_type, "")) if m.message_type != "sticker" else "😀 stiker"
    if len(preview) > 160:
        preview = preview[:157] + "…"
    who = f"{u.full_name or 'Mijoz'} ({u.phone_number})" if u else "Mijoz"
    return f"💬 <b>Javobsiz chat — {minutes} daqiqa</b>\n👤 {escape(who)}\n«{escape(preview)}»"


def alert_waiting() -> dict:
    """
    Posts each support chat waiting longer than the threshold to Telegram (once per waiting message): to
    NutriZoneAnalyticsBot's recipients when that bot is configured, otherwise to the Orders bot's staff channel.
    """
    from apps.telegram_bot.infrastructure import analytics_bot

    cfg = chat_settings()
    chat = getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", None)
    analytics = analytics_bot.is_configured()
    if not cfg.alert_enabled or not (chat or analytics):
        return {"sent": 0, "reason": "disabled" if not cfg.alert_enabled else "no channel"}
    if cfg.alert_only_work_hours and not is_open(cfg=cfg):
        return {"sent": 0, "reason": "out of hours"}
    from apps.notifications.infrastructure import composition

    sent = 0
    for item in waiting_conversations(timedelta(minutes=max(cfg.alert_after_minutes, 1)))[:10]:
        if not _log("alert", str(item["message"].pk), item["conversation_id"]):
            continue
        try:
            if analytics:
                if analytics_bot.chat_alert(_analytics_alert_text(item), item["conversation_id"]):
                    sent += 1
                continue
            composition.build_orders_telegram_gateway().send_message_with_keyboard(str(chat), _alert_text(item), _desk_button(item["conversation_id"]))
            sent += 1
        except Exception:  # noqa: BLE001 - one failed post never stops the others
            logger.exception("chat: waiting alert failed for %s", item["conversation_id"])
    return {"sent": sent, "via": "analytics" if analytics else "orders"}


def _analytics_alert_text(item) -> str:
    from html import escape

    from apps.identity.infrastructure.models import User
    from apps.telegram_bot.infrastructure.analytics_bot import customer_label, preview

    m = item["message"]
    minutes = int((timezone.now() - m.created_at).total_seconds() // 60)
    who = customer_label(User.objects.filter(id=item["customer_id"]).first())
    return f"💬 <b>Javobsiz chat — {minutes} daqiqa</b>\n👤 {escape(who)}\n«{escape(preview(m))}»"


# ---------------------------------------------------------------- cards


def card_payload(content: str | None, viewer_id=None) -> dict | None:
    """A CARD message's content ("product:<uuid>" / "order:<uuid>") → what both sides see. None when it no longer exists."""
    from apps.chat.domain.value_objects import CARD_REF

    if not content or not CARD_REF.match(content):
        return None
    kind, ref = content.split(":", 1)
    try:
        return _product_card(uuid.UUID(ref)) if kind == "product" else _order_card(uuid.UUID(ref))
    except Exception:  # noqa: BLE001 - a card that can't be resolved renders as "not available", never an error
        logger.exception("chat: card %s could not be resolved", content)
        return None


def _media(path: str) -> str:
    if not path or path.startswith(("http://", "https://")):
        return path
    base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
    return f"{base}{settings.MEDIA_URL}{path}"


def _product_card(product_id) -> dict | None:
    from apps.products.infrastructure.models import Product, ProductMedia, ProductTranslation
    from apps.products.infrastructure.selectors import bulk_variant_prices

    product = Product.objects.filter(pk=product_id).prefetch_related("variants").first()
    if product is None:
        return None
    names = {t.locale_code: t for t in ProductTranslation.objects.filter(product=product)}
    tr = names.get("uz") or next(iter(names.values()), None)
    media = ProductMedia.objects.filter(product=product).order_by("sort_order").values("storage_path", "thumbnail_paths").first()
    variants = [v for v in product.variants.all() if v.status == "active"]
    default = next((v for v in variants if v.is_default), variants[0] if variants else None)
    price = bulk_variant_prices([default.id]).get(default.id) if default else None
    from apps.stores.infrastructure.availability import sellable

    stock = sum(sellable([v.id for v in variants]).values()) if variants else 0
    return {
        "kind": "product", "id": str(product.id), "title": tr.name if tr else "Mahsulot", "names": {k: v.name for k, v in names.items()},
        "image": _media(((media or {}).get("thumbnail_paths") or {}).get("medium") or (media or {}).get("storage_path") or ""),
        "price": str(price["amount"]) if price else None, "currency": price["currency"] if price else "UZS", "in_stock": stock > 0,
        "url": f"/products/{tr.slug}" if tr and tr.slug else "/products", "published": product.status == "published",
    }


ORDER_STATUS = {"pending_payment": "To'lov kutilmoqda", "confirmed": "Tasdiqlandi", "processing": "Yig'ilmoqda", "shipped": "Yo'lda", "delivered": "Yetkazildi",
                "completed": "Yakunlandi", "cancelled": "Bekor qilingan", "returned": "Qaytarilgan", "failed": "Muvaffaqiyatsiz"}


def _order_card(order_id) -> dict | None:
    from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum

    from apps.ordering.infrastructure.models import OrderLineItemModel, OrderModel

    order = OrderModel.objects.filter(pk=order_id).first()
    if order is None:
        return None
    expr = ExpressionWrapper(F("unit_price_amount") * F("quantity") - F("discount_amount") + F("tax_amount"), output_field=DecimalField(max_digits=16, decimal_places=2))
    agg = OrderLineItemModel.objects.filter(order=order, status="active").aggregate(total=Sum(expr), items=Count("id"), units=Sum("quantity"))
    return {
        "kind": "order", "id": str(order.id), "title": order.order_number, "status": order.status, "status_label": ORDER_STATUS.get(order.status, order.status),
        "total": str(agg["total"] or 0), "currency": order.currency, "items": agg["items"] or 0, "units": agg["units"] or 0,
        "date": timezone.localtime(order.created_at, TZ).strftime("%d.%m.%Y"), "url": f"/orders/{order.order_number}",
        "eta": (lambda d: d.strftime("%d.%m.%Y") if d else None)(delivery_eta(order)), "customer_id": str(order.customer_id) if order.customer_id else None,
    }


def delivery_eta(order, cfg=None) -> date | None:
    """The estimated delivery day of an order still on its way: placed + `delivery_days` (a Sunday moves to Monday, never in the past)."""
    if order.status in ("draft", "delivered", "completed", "cancelled", "returned", "failed"):
        return None
    cfg = cfg or chat_settings()
    day = timezone.localtime(order.placed_at or order.created_at, TZ).date() + timedelta(days=cfg.delivery_days)
    if day.weekday() == 6:
        day += timedelta(days=1)
    return max(day, timezone.localdate(timezone=TZ))


def _delivered_on(order) -> date | None:
    from apps.ordering.infrastructure.models import OrderStatusHistoryEntryModel

    at = OrderStatusHistoryEntryModel.objects.filter(order=order, to_status="delivered").order_by("-changed_at").values_list("changed_at", flat=True).first()
    return timezone.localtime(at, TZ).date() if at else None


# ---------------------------------------------------------------- quick-reply variables

VARIABLES = {  # {name} → what the desk fills in, per conversation
    "ism": "Mijozning ismi", "buyurtma_raqami": "Oxirgi buyurtma raqami", "buyurtma_holati": "Oxirgi buyurtma holati",
    "yetkazish_sanasi": "Taxminiy yetkazish sanasi", "operator": "Javob berayotgan xodim", "ish_vaqti": "Ish vaqti",
}
VARIABLE_RE = re.compile(r"\{(" + "|".join(VARIABLES) + r")\}")


def template_vars(conversation_id, operator_name: str | None = None) -> dict:
    """Values of the quick-reply variables for one support chat (None = unknown, e.g. no orders yet)."""
    from apps.chat.infrastructure.models import ParticipantModel
    from apps.identity.infrastructure.models import User
    from apps.ordering.infrastructure.models import OrderModel

    customer_id = ParticipantModel.objects.filter(conversation_id=conversation_id, role="customer").values_list("user_id", flat=True).first()
    u = User.objects.filter(id=customer_id).first() if customer_id else None
    order = OrderModel.objects.filter(customer_id=customer_id).exclude(status="draft").order_by("-created_at").first() if customer_id else None
    cfg = chat_settings()
    eta = (delivery_eta(order, cfg) or _delivered_on(order)) if order else None
    return {
        "ism": ((u.full_name or "").split() or [None])[0] if u else None,
        "buyurtma_raqami": order.order_number if order else None,
        "buyurtma_holati": ORDER_STATUS.get(order.status, order.status).lower() if order else None,
        "yetkazish_sanasi": eta.strftime("%d.%m.%Y") if eta else None,
        "operator": operator_name or None,
        "ish_vaqti": hours_label(cfg),
    }


def render_template(text: str, values: dict) -> tuple[str, list[str]]:
    """Fills the known {variables}; returns the text and the variables that had no value (left as they are)."""
    missing: list[str] = []

    def sub(m):
        value = values.get(m.group(1))
        if value in (None, ""):
            missing.append(m.group(1))
            return m.group(0)
        return str(value)

    return VARIABLE_RE.sub(sub, text or ""), sorted(set(missing))


# ---------------------------------------------------------------- order bot ("Buyurtmam qayerda?")

ORDER_NUMBER_RE = re.compile(r"\bORD-[A-Z0-9]{6,}\b", re.I)
_ORDER_WORD = re.compile(r"(buyurtm|buyirtm|zakaz|буюртм|заказ|\border)", re.I)
_STATUS_WORD = re.compile(r"(qayer|qaer|holat|kelad|kelmad|kelmay|yetib|qani|где|статус|отслед|придет|придёт|привез|where|status|track)", re.I)
ACTIVE_ORDER = ("pending_payment", "confirmed", "processing", "shipped")
BOT_GAP = timedelta(minutes=10)
BOT_TEXT = {
    "uz": "🤖 Buyurtmangiz holati quyida. Boshqa savolingiz bo'lsa, yozing — operator javob beradi.",
    "ru": "🤖 Статус вашего заказа ниже. Если остались вопросы — напишите, оператор ответит.",
    "en": "🤖 Here is your order status. Any other question? Write it — an operator will reply.",
}


def asks_order_status(text: str) -> bool:
    text = (text or "").strip()
    return 0 < len(text) <= 200 and bool(_ORDER_WORD.search(text) and _STATUS_WORD.search(text))


def maybe_order_bot(message_id) -> bool:
    """A customer asking where their order is (or writing its number) → the bot answers at once with the order card(s)."""
    from apps.chat.domain.enums import MessageType
    from apps.chat.infrastructure import composition
    from apps.chat.infrastructure.models import ChatAutomationLog, ConversationModel, MessageModel, ParticipantModel
    from apps.chat.infrastructure.realtime import message_payload, push_message
    from apps.ordering.infrastructure.models import OrderModel

    message = MessageModel.objects.filter(pk=message_id, message_type="text").first()
    if message is None or not chat_settings().order_bot_enabled:
        return False
    conv = ConversationModel.objects.filter(pk=message.conversation_id, status="open", conversation_type="customer_support").first()
    if conv is None or not ParticipantModel.objects.filter(conversation_id=conv.id, user_id=message.sender_id, role="customer").exists():
        return False
    mine = OrderModel.objects.filter(customer_id=message.sender_id).exclude(status="draft")
    numbers = [n.upper() for n in ORDER_NUMBER_RE.findall(message.content or "")]
    if numbers:
        orders = list(mine.filter(order_number__in=numbers)[:3])  # only the customer's own orders, never someone else's by number
    elif asks_order_status(message.content):
        if ChatAutomationLog.objects.filter(kind="order_bot", conversation_id=conv.id, created_at__gte=timezone.now() - BOT_GAP).exists():
            return False  # answered a moment ago -- the customer is talking to a human now
        orders = list(mine.filter(status__in=ACTIVE_ORDER).order_by("-created_at")[:3]) or list(mine.order_by("-created_at")[:1])
    else:
        return False
    if not orders or not _log("order_bot", str(message.id), conv.id):
        return False  # no order to show: the operator answers
    members = list(ParticipantModel.objects.filter(conversation_id=conv.id, removed_at__isnull=True).values_list("user_id", flat=True))
    send = composition.build_send_message(BOT_ID)
    lang = _customer_language(message.sender_id)
    for kind, content in [(MessageType.SYSTEM, BOT_TEXT.get(lang, BOT_TEXT["uz"]))] + [(MessageType.CARD, f"order:{o.id}") for o in orders]:
        reply = send.execute(conversation_id=conv.id, sender_id=BOT_ID, message_type=kind, content=content)
        push_message(conv.id, message_payload(reply), BOT_ID, members)
    return True
