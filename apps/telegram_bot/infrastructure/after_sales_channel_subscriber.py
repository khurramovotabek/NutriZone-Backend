"""
Telegram Orders Channel -- customer after-sales requests.

Tells the store team, in the same Orders Channel as new orders, the moment a customer:
  * asks for a return            (ReturnRequested,        by_customer)
  * asks to cancel a parcel that is already being packed / on the way (CancellationRequested, by_customer)
  * cancels an order themselves  (OrderCancelled,         by_customer) -- so nobody packs it.

Staff-created requests are not announced (the staff member is already on it). Same proven shape as the POS
subscriber: an independent keyset cursor through Ordering's outbox (row id=3 of TelegramOrdersChannelCursor),
check-before-send, and TelegramAfterSalesChannelMessage.event_key as the exactly-once guard. Requests get a
"Tasdiqlash" button (handled in interfaces/callback_router.py) and a Dashboard link; rejecting needs a reason,
so it is done in the dashboard.
"""
from __future__ import annotations

import html
import logging
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.notifications.infrastructure.gateways import TelegramGatewayRetryableError
from apps.telegram_bot.infrastructure import models as telegram_orm

logger = logging.getLogger("nutrizone.app")

AFTER_SALES_CURSOR_ID = 3  # 1 = online orders, 2 = POS sales
EVENT_TYPES = ("ReturnRequested", "CancellationRequested", "OrderCancelled")
_BATCH_SIZE = 100

RETURN_REASONS = {
    "defective": "Nuqsonli", "wrong_item": "Boshqa mahsulot keldi", "not_as_described": "Tavsifga mos emas",
    "changed_mind": "Fikrini o'zgartirdi", "damaged_in_transit": "Yo'lda shikastlangan", "other": "Boshqa sabab",
}
STATUS_UZ = {"pending_payment": "To'lov kutilmoqda", "confirmed": "Tasdiqlangan", "processing": "Yig'ilmoqda", "shipped": "Yo'lda", "delivered": "Yetkazilgan", "completed": "Yakunlangan"}


def sync_after_sales_channel() -> dict:
    orders_chat_id = getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", None)
    if not orders_chat_id:
        return {"scanned": 0, "posted": 0, "skipped_no_channel": True}

    from apps.ordering.infrastructure import models as ordering_orm

    events_qs = ordering_orm.OrderingOutboxEvent.objects.filter(event_type__in=EVENT_TYPES)
    cursor, created = telegram_orm.TelegramOrdersChannelCursor.objects.get_or_create(id=AFTER_SALES_CURSOR_ID)
    if created:
        # Normally created by migration 0007; never replay history into the live channel.
        latest = events_qs.order_by("-created_at", "-id").first()
        if latest is not None:
            cursor.last_processed_created_at, cursor.last_processed_id = latest.created_at, latest.id
            cursor.save(update_fields=["last_processed_created_at", "last_processed_id", "updated_at"])
        return {"scanned": 0, "posted": 0, "initialized": True}

    qs = events_qs
    if cursor.last_processed_created_at is not None:
        qs = qs.filter(created_at__gte=cursor.last_processed_created_at).exclude(created_at=cursor.last_processed_created_at, id=cursor.last_processed_id)
    events = list(qs.order_by("created_at", "id")[:_BATCH_SIZE])

    posted = skipped = 0
    last_successful = None
    for event in events:
        try:
            outcome = post_event(event.event_type, event.payload or {}, str(orders_chat_id))
            posted += outcome == "posted"
            skipped += outcome != "posted"
            last_successful = event
        except TelegramGatewayRetryableError:
            logger.warning("After-sales channel: retryable failure for event %s, will retry next run.", event.id)
            break
        except Exception:  # noqa: BLE001 -- one bad event must not block the channel
            logger.exception("After-sales channel: unexpected failure for event %s", event.id)
            last_successful = event

    if last_successful is not None:
        cursor.last_processed_created_at, cursor.last_processed_id = last_successful.created_at, last_successful.id
        cursor.save(update_fields=["last_processed_created_at", "last_processed_id", "updated_at"])
    return {"scanned": len(events), "posted": posted, "skipped": skipped}


def _money(amount) -> str:
    return f"{int(round(Decimal(amount or 0))):,}".replace(",", " ") + " so'm"


def _customer(order) -> str:
    from apps.identity.infrastructure.models import User

    user = User.objects.filter(id=order.customer_id).only("full_name", "phone_number").first() if order.customer_id else None
    name = (user.full_name if user else "") or order.shipping_recipient_name or "Mijoz"
    phone = (user.phone_number if user else "") or order.shipping_phone or "—"
    return f"\U0001F464 {html.escape(name)}\n\U0001F4DE {html.escape(phone)}"


def _items(order, picked: dict) -> tuple[str, Decimal]:
    """picked = {order_line_item_id: qty} (empty = every active line). Returns the bullet list and the value the customer paid for them."""
    from apps.stores.infrastructure.stock_service import variant_infos

    lines = [l for l in order.lines.all() if (l.id in picked if picked else l.status == "active")]
    infos = variant_infos({l.product_variant_id for l in lines})
    out, value = [], Decimal(0)
    for l in lines:
        qty = picked.get(l.id, l.quantity) if picked else l.quantity
        unit = (l.unit_price_amount * l.quantity - l.discount_amount + l.tax_amount) / (l.quantity or 1)
        value += unit * qty
        info = infos.get(l.product_variant_id)
        name = info.name if info else str(l.product_variant_id)[:8]
        size = f" ({info.size})" if info and info.size else ""
        out.append(f"• {html.escape(name)}{html.escape(size)} — {qty} dona")
    return "\n".join(out), value


def _comment(note: str) -> str:
    from apps.ordering.infrastructure.after_sales import CUSTOMER_COMMENT_PREFIX

    text = (note or "").strip()
    if text.startswith(CUSTOMER_COMMENT_PREFIX):
        text = text[len(CUSTOMER_COMMENT_PREFIX):].strip()
    return f"\n\U0001F4AC <i>{html.escape(text[:600])}</i>" if text else ""


def _dashboard(path: str) -> dict | None:
    base = getattr(settings, "PUBLIC_BASE_URL", None)
    return {"text": "\U0001F5A5 Dashboard", "url": f"{base.rstrip('/')}{path}"} if base else None


def build_message(event_type: str, payload: dict):
    """(event_key, text, keyboard) for one outbox event, or None when it isn't a customer action worth announcing."""
    from apps.ordering.infrastructure import models as o

    if not payload.get("by_customer"):
        return None
    if event_type == "ReturnRequested":
        ret = o.OrderReturnModel.objects.filter(id=payload.get("return_id")).prefetch_related("lines").first()
        order = o.OrderModel.objects.filter(id=ret.order_id).first() if ret else None
        if ret is None or order is None:
            return None
        items, value = _items(order, {l.order_line_item_id: l.quantity for l in ret.lines.all()})
        text = (
            f"\U0001F504 <b>QAYTARISH SO'ROVI</b>\n\n"
            f"\U0001F9FE {ret.return_number} · buyurtma {order.order_number}\n{_customer(order)}\n"
            f"\U0001F3F7 Sabab: {RETURN_REASONS.get(ret.reason, ret.reason)}\n\n"
            f"\U0001F6CD Qaytariladi:\n{items}\n\U0001F4B0 Qiymati: {_money(value)}{_comment(ret.note)}"
        )
        row = [{"text": "✅ Tasdiqlash", "callback_data": f"manager:ret_ok:{ret.id}"}]
        link = _dashboard(f"/django-admin/ordering/orderreturnmodel/{ret.id}/change/")
        return f"return:{ret.id}", text, [row + ([link] if link else [])]
    if event_type == "CancellationRequested":
        can = o.OrderCancellationModel.objects.filter(id=payload.get("cancellation_id")).prefetch_related("lines").first()
        order = o.OrderModel.objects.filter(id=can.order_id).first() if can else None
        if can is None or order is None:
            return None
        items, value = _items(order, {l.order_line_item_id: l.quantity for l in can.lines.all()})
        text = (
            f"⛔ <b>BEKOR QILISH SO'ROVI</b>\n\n"
            f"\U0001F9FE {order.order_number} · {STATUS_UZ.get(order.status, order.status)}\n{_customer(order)}\n\n"
            f"\U0001F6CD {items}\n\U0001F4B0 {_money(value)}{_comment(can.note)}\n\n"
            f"⚠️ Buyurtma allaqachon yig'ilmoqda yoki yo'lda — tez hal qiling."
        )
        row = [{"text": "✅ Bekor qilishni tasdiqlash", "callback_data": f"manager:can_ok:{can.id}"}]
        link = _dashboard(f"/django-admin/ordering/ordercancellationmodel/{can.id}/change/")
        return f"cancellation:{can.id}", text, [row + ([link] if link else [])]
    if event_type == "OrderCancelled":
        order = o.OrderModel.objects.filter(id=payload.get("order_id")).first()
        if order is None:
            return None
        items, value = _items(order, {l.id: l.quantity for l in order.lines.all()})
        text = (
            f"❌ <b>MIJOZ BUYURTMANI BEKOR QILDI</b>\n\n"
            f"\U0001F9FE {order.order_number}\n{_customer(order)}\n\n\U0001F6CD {items}\n\U0001F4B0 {_money(value)}"
            f"{_comment(order.note.split(chr(10))[-1] if order.note else '')}\n\n"
            f"ℹ️ Ombordagi band qilingan mahsulot avtomatik bo'shatildi — yig'mang."
        )
        link = _dashboard(f"/django-admin/ordering/ordermodel/{order.id}/change/")
        return f"order_cancel:{order.id}", text, [[link]] if link else []
    return None


def post_event(event_type: str, payload: dict, chat_id: str) -> str:
    built = build_message(event_type, payload)
    if built is None:
        return "skipped"
    key, text, keyboard = built
    if telegram_orm.TelegramAfterSalesChannelMessage.objects.filter(event_key=key).exists():
        return "skipped"
    from apps.notifications.infrastructure import composition as notifications_composition

    message_id = notifications_composition.build_orders_telegram_gateway().send_message_with_keyboard(chat_id, text, keyboard)
    try:
        with transaction.atomic():
            telegram_orm.TelegramAfterSalesChannelMessage.objects.create(event_key=key, chat_id=chat_id, message_id=str(message_id))
    except IntegrityError:
        return "skipped"
    return "posted"
