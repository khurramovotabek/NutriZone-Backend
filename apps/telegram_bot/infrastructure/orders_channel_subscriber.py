"""
Telegram Orders Channel subscriber -- Phase 15E.

Matches the exact, proven outbox-cursor pattern already established
by order_confirmed_subscriber.py (Phase 02G) and
telegram_dispatch_subscriber.py (Phase 15): an independent keyset
cursor through Ordering's own outbox, filtered to OrderCreated, with
exactly-once posting enforced by TelegramOrderChannelMessage's own
primary key on order_id (a duplicate replay hits this constraint
before a second message is ever sent).
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.db import IntegrityError, transaction

from apps.notifications.infrastructure.gateways import (
    TelegramGatewayNonRetryableError,
    TelegramGatewayRetryableError,
)
from apps.telegram_bot.infrastructure import models as telegram_orm

logger = logging.getLogger("nutrizone.app")

_BATCH_SIZE = 100


def sync_orders_channel() -> dict:
    orders_chat_id = getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", None)
    if not orders_chat_id:
        return {"scanned": 0, "posted": 0, "skipped_no_channel": True}

    cursor, _created = telegram_orm.TelegramOrdersChannelCursor.objects.get_or_create(id=1)

    from apps.ordering.infrastructure import models as ordering_orm

    qs = ordering_orm.OrderingOutboxEvent.objects.filter(event_type="OrderCreated")
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
            outcome = _post_one(event.payload, orders_chat_id)
            if outcome == "posted":
                posted += 1
            else:
                skipped += 1
            last_successful = event
        except TelegramGatewayRetryableError:
            logger.warning("Orders Channel: retryable failure for event %s, will retry next run.", event.id)
            break
        except Exception:  # noqa: BLE001
            logger.exception("Orders Channel: unexpected failure for event %s", event.id)
            last_successful = event

    if last_successful is not None:
        cursor.last_processed_created_at = last_successful.created_at
        cursor.last_processed_id = last_successful.id
        cursor.save(update_fields=["last_processed_created_at", "last_processed_id", "updated_at"])

    return {"scanned": len(events), "posted": posted, "skipped": skipped}


def _post_one(payload: dict, orders_chat_id: str) -> str:
    from apps.notifications.infrastructure import composition as notifications_composition
    from apps.ordering.infrastructure import composition as ordering_composition

    order_id = payload["order_id"]

    order = ordering_composition.build_order_repository().get_by_id(order_id)
    if order is None:
        return "skipped"

    # Check-before-send: a duplicate cursor replay must not re-send the
    # actual Telegram message, only re-attempting the DB bookkeeping
    # afterward would still leave a real duplicate customer/manager-facing
    # message (confirmed by a real test failure before this fix).
    if telegram_orm.TelegramOrderChannelMessage.objects.filter(order_id=order_id).exists():
        return "skipped"

    from apps.telegram_bot.infrastructure import orders_post

    card = orders_post.build(order)
    text, keyboard, address, has_point = card["text"], orders_post.open_keyboard(order, card), card["address"], card["has_point"]
    # a photo caption is capped at 1024 characters -- a bigger order goes out as a text message
    first_image_url = card["image"] if orders_post.fits_caption(text) else None

    message_id = _send_rich(order.id, orders_chat_id, keyboard)
    if message_id:
        try:
            with transaction.atomic():
                telegram_orm.TelegramOrderChannelMessage.objects.create(order_id=order_id, chat_id=str(orders_chat_id), message_id=message_id)
        except IntegrityError:
            return "skipped"
        return "posted"

    gateway = notifications_composition.build_orders_telegram_gateway()
    if first_image_url:
        try:
            message_id = gateway.send_photo(str(orders_chat_id), first_image_url, text, inline_keyboard=keyboard)
        except TelegramGatewayNonRetryableError:
            # The manager must still be notified of a real new order even
            # if the product image itself is unreachable/unfetchable by
            # Telegram's own servers (confirmed real failure: Cloudflare
            # Quick Tunnel media URL intermittently rejected with "failed
            # to get HTTP URL content") -- silently dropping the whole
            # notification here previously lost the order permanently,
            # since the caller (sync_orders_channel) advances its cursor
            # past this event on any non-retryable exception.
            logger.warning(
                "Orders Channel: send_photo failed for order %s, falling back to text-only message.",
                order_id,
            )
            message_id = gateway.send_message_with_keyboard(str(orders_chat_id), text, keyboard)
    else:
        message_id = gateway.send_message_with_keyboard(str(orders_chat_id), text, keyboard)

    if has_point:  # an exact pin right under the order: one tap opens it in the phone's map app
        try:
            gateway.send_venue(str(orders_chat_id), address.latitude, address.longitude, f"{order.order_number.value} · {address.recipient_name or ''}".strip(" ·"),
                               ", ".join(x for x in (address.line1, address.line2, address.city) if x), reply_to=message_id)
        except Exception:  # noqa: BLE001 - the order message itself is already out; the pin is a bonus
            logger.warning("Orders Channel: send_venue failed for order %s", order_id, exc_info=True)

    try:
        with transaction.atomic():
            telegram_orm.TelegramOrderChannelMessage.objects.create(order_id=order_id, chat_id=str(orders_chat_id), message_id=message_id)
    except IntegrityError:
        return "skipped"

    return "posted"


def _send_rich(order_id, chat_id, keyboard) -> int | None:
    """The premium rich post (orders_rich.order_doc: picture, tables, live map, coins/cash split). None = use the classic post."""
    from apps.telegram_bot.infrastructure import orders_bot, orders_rich
    from apps.telegram_bot.infrastructure import rich as R

    if not orders_bot.token() or getattr(settings, "NUTRIZONE_TELEGRAM_GATEWAY", "disabled") != "live":
        return None
    try:
        doc, _meta = orders_rich.order_doc(order_id)
        if doc is None:
            return None
        doc.fallback = ""  # a refusal falls back to the classic photo/text post below, not to a second rich attempt
        return R.send(orders_bot.token(), chat_id, doc, keyboard) or None
    except Exception:  # noqa: BLE001
        logger.warning("Orders Channel: rich post failed for order %s -- sending the classic post", order_id, exc_info=True)
        return None
