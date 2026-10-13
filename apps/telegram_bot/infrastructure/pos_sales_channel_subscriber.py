"""
Telegram Orders Channel -- POS Terminal sales.

Posts every completed POS sale to the same Orders Channel (and through
the same Orders Bot) as online orders, clearly marked "POS Terminal
orqali", plus a short notice when a sale is later refunded from the
admin. Mirrors orders_channel_subscriber.py's proven shape: an
independent keyset cursor through POS's own outbox (row id=2 of
TelegramOrdersChannelCursor), check-before-send, and a unique
(sale_id, kind) record as the exactly-once guard.

Differences from the online-order post, by design:
- no map/location and no address: an in-store sale has none;
- no Confirm/Cancel buttons: the sale is already paid and completed --
  only a Dashboard link to the sale itself;
- the buyer is the sale's own `identity.User` (name + phone), not a
  shipping address recipient.
"""
from __future__ import annotations

import html
import logging
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.notifications.infrastructure.gateways import (
    TelegramGatewayNonRetryableError,
    TelegramGatewayRetryableError,
)
from apps.telegram_bot.infrastructure import models as telegram_orm

logger = logging.getLogger("nutrizone.app")

POS_CURSOR_ID = 2  # id=1 is the online-orders cursor (orders_channel_subscriber.py)
_BATCH_SIZE = 100
_EVENT_KINDS = {"SaleCompleted": telegram_orm.TelegramPosSaleChannelMessage.KIND_COMPLETED, "SaleRefunded": telegram_orm.TelegramPosSaleChannelMessage.KIND_REFUNDED}
_STORE_TZ = ZoneInfo("Asia/Tashkent")


def sync_pos_sales_channel() -> dict:
    orders_chat_id = getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", None)
    if not orders_chat_id:
        return {"scanned": 0, "posted": 0, "skipped_no_channel": True}

    from apps.pos.infrastructure import models as pos_orm

    events_qs = pos_orm.PosOutboxEvent.objects.filter(event_type__in=list(_EVENT_KINDS))
    cursor, created = telegram_orm.TelegramOrdersChannelCursor.objects.get_or_create(id=POS_CURSOR_ID)
    if created:
        # Safety net for a missing cursor row (normally created by migration
        # 0006): start at the newest existing event rather than replaying
        # the whole POS history into the live channel.
        latest = events_qs.order_by("-created_at", "-id").first()
        if latest is not None:
            cursor.last_processed_created_at, cursor.last_processed_id = latest.created_at, latest.id
            cursor.save(update_fields=["last_processed_created_at", "last_processed_id", "updated_at"])
        return {"scanned": 0, "posted": 0, "initialized": True}

    qs = events_qs
    if cursor.last_processed_created_at is not None:
        qs = qs.filter(created_at__gte=cursor.last_processed_created_at).exclude(
            created_at=cursor.last_processed_created_at, id=cursor.last_processed_id
        )
    events = list(qs.order_by("created_at", "id")[:_BATCH_SIZE])

    posted = 0
    skipped = 0
    last_successful = None
    for event in events:
        try:
            outcome = _post_one(event.event_type, event.payload, str(orders_chat_id))
            posted += outcome == "posted"
            skipped += outcome != "posted"
            last_successful = event
        except TelegramGatewayRetryableError:
            logger.warning("POS Orders Channel: retryable failure for event %s, will retry next run.", event.id)
            break
        except Exception:  # noqa: BLE001 -- one bad sale must not block the channel
            logger.exception("POS Orders Channel: unexpected failure for event %s", event.id)
            last_successful = event

    if last_successful is not None:
        cursor.last_processed_created_at = last_successful.created_at
        cursor.last_processed_id = last_successful.id
        cursor.save(update_fields=["last_processed_created_at", "last_processed_id", "updated_at"])

    return {"scanned": len(events), "posted": posted, "skipped": skipped}


def _money(amount) -> str:
    return f"{int(round(Decimal(amount or 0))):,}".replace(",", " ") + " so'm"


def _order_number(sale_id) -> str:
    return "#" + str(sale_id)[:8].upper()


def _customer_lines(sale) -> str:
    from apps.identity.infrastructure.models import User

    customer = User.objects.filter(id=sale.customer_id).only("full_name", "phone_number").first() if sale.customer_id else None
    name = (customer.full_name if customer else "") or "Noma'lum"
    phone = (customer.phone_number if customer else "") or "—"
    return f"\U0001F464 {html.escape(name)}\n\U0001F4DE {html.escape(phone)}"


def _post_one(event_type: str, payload: dict, orders_chat_id: str) -> str:
    from apps.pos.infrastructure import models as pos_orm

    kind = _EVENT_KINDS[event_type]
    sale_id = payload["sale_id"]
    if telegram_orm.TelegramPosSaleChannelMessage.objects.filter(sale_id=sale_id, kind=kind).exists():
        return "skipped"

    sale = pos_orm.SaleModel.objects.filter(id=sale_id).prefetch_related("line_items").first()
    if sale is None:
        return "skipped"

    if kind == telegram_orm.TelegramPosSaleChannelMessage.KIND_COMPLETED:
        message_id = _send_rich(sale.id, orders_chat_id)
        if message_id:
            try:
                with transaction.atomic():
                    telegram_orm.TelegramPosSaleChannelMessage.objects.create(sale_id=sale.id, kind=kind, chat_id=orders_chat_id, message_id=message_id)
            except IntegrityError:
                return "skipped"
            return "posted"
        text, image_url = _completed_message(sale)
    else:
        text, image_url = _refunded_message(sale), None

    keyboard = []
    public_base_url = getattr(settings, "PUBLIC_BASE_URL", None)
    if public_base_url:
        keyboard = [[{"text": "\U0001F5A5 Dashboard", "url": f"{public_base_url.rstrip('/')}/django-admin/pos/salemodel/{sale.id}/change/"}]]

    from apps.notifications.infrastructure import composition as notifications_composition

    gateway = notifications_composition.build_orders_telegram_gateway()
    if image_url:
        try:
            message_id = gateway.send_photo(orders_chat_id, image_url, text, inline_keyboard=keyboard or None)
        except TelegramGatewayNonRetryableError:
            # Same fallback as the online-order post: an unreachable product
            # image must never cost the manager the notification itself.
            logger.warning("POS Orders Channel: send_photo failed for sale %s, falling back to text-only message.", sale.id)
            message_id = gateway.send_message_with_keyboard(orders_chat_id, text, keyboard)
    else:
        message_id = gateway.send_message_with_keyboard(orders_chat_id, text, keyboard)

    try:
        with transaction.atomic():
            telegram_orm.TelegramPosSaleChannelMessage.objects.create(sale_id=sale.id, kind=kind, chat_id=orders_chat_id, message_id=message_id)
    except IntegrityError:
        return "skipped"
    return "posted"


def _completed_message(sale) -> tuple[str, str | None]:
    from apps.products.infrastructure.selectors import ProductDetailSelector

    selector = ProductDetailSelector()
    lines_text = []
    first_image_url = None
    products_total = Decimal("0")
    for line in sale.line_items.all():
        product = selector.get_by_id(line.product_id, locale="uz")
        name = product["name"] if product and product.get("name") else "Noma'lum mahsulot"
        if first_image_url is None and product and product.get("primary_image_path"):
            first_image_url = product["primary_image_path"]
        line_total = line.unit_price_amount * line.quantity
        products_total += line_total
        lines_text.append(f"• {html.escape(name)} — {line.quantity} x {_money(line.unit_price_amount)}")

    delivery = sale.delivery_fee_amount or Decimal("0")
    moment = timezone.localtime(sale.completed_at or sale.created_at, _STORE_TZ)
    text = (
        "\U0001F195 <b>YANGI BUYURTMA</b>\n"
        "\U0001F5A5 <b>POS Terminal orqali</b>\n\n"
        f"\U0001F9FE {_order_number(sale.id)}\n"
        f"{_customer_lines(sale)}\n\n"
        "\U0001F6CD Mahsulotlar:\n" + "\n".join(lines_text) + "\n\n"
        + (f"\U0001F69A Yetkazib berish: {_money(delivery)}\n" if delivery else "")
        + f"\U0001F4B0 <b>Jami: {_money(products_total + delivery)}</b>\n"
        "\U0001F4B5 To'lov: Naqd\n"
        f"\U0001F552 {moment:%d.%m.%Y %H:%M}"
    )
    return text, first_image_url


def _refunded_message(sale) -> str:
    products_total = sum((li.unit_price_amount * li.quantity for li in sale.line_items.all()), Decimal("0"))
    moment = timezone.localtime(sale.refunded_at or timezone.now(), _STORE_TZ)
    return (
        "↩️ <b>BUYURTMA QAYTARILDI</b>\n"
        "\U0001F5A5 <b>POS Terminal orqali</b>\n\n"
        f"\U0001F9FE {_order_number(sale.id)}\n"
        f"{_customer_lines(sale)}\n\n"
        f"\U0001F4B8 Qaytarilgan mahsulotlar summasi: <b>{_money(products_total)}</b>\n"
        f"\U0001F552 {moment:%d.%m.%Y %H:%M}"
    )


def _send_rich(sale_id, chat_id) -> int | None:
    """Premium rich post (orders_rich.sale_doc): branch, cashier, customer, basket with stock left, coins vs money split."""
    from apps.telegram_bot.infrastructure import orders_bot, orders_rich
    from apps.telegram_bot.infrastructure import rich as R

    if not orders_bot.token() or getattr(settings, "NUTRIZONE_TELEGRAM_GATEWAY", "disabled") != "live":
        return None
    try:
        doc, keyboard = orders_rich.sale_doc(sale_id)
        if doc is None:
            return None
        doc.fallback = ""
        return R.send(orders_bot.token(), chat_id, doc, keyboard) or None
    except Exception:  # noqa: BLE001
        logger.warning("POS Orders Channel: rich post failed for sale %s -- sending the classic post", sale_id, exc_info=True)
        return None
