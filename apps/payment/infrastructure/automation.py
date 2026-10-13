"""
Unpaid online orders: a reminder with "Pay" buttons, then automatic cancellation.

An order is *awaiting online payment* when it is still `pending_payment`, the customer started an online
payment (a Payme / Click / Uzum attempt exists), the latest attempt is still open and nothing was paid.
Choosing cash ("💵 Naqd to'layman") closes the open attempts, so the order leaves this flow and goes to
the operators as a normal cash-on-delivery order. Timings live in PaymentSettings (Dashboard → To'lovlar).

Cancellation goes through the ordering CancelOrder service with the production context, so reserved stock
is released and redeemed coins come back exactly as for any other cancellation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db.models import Min
from django.utils import timezone

from apps.payment.infrastructure import service
from apps.payment.infrastructure.models import PaymentModel, PaymentSettings, PaymentStatusChoices
from apps.payment.infrastructure.providers import registry

logger = logging.getLogger("nutrizone.app")

PROVIDER_HOLD = {"payme": timedelta(hours=12), "uzum": timedelta(hours=12), "click": timedelta(hours=1)}

TEXT = {
    "reminder": {
        "uz": "⏳ <b>{order} buyurtmasi to'lovni kutmoqda</b>\n\n💰 Summa: <b>{amount} so'm</b>\n💳 Usul: {provider}\n\nTo'lov {hours} soat ichida qilinmasa, buyurtma avtomatik bekor qilinadi.",
        "ru": "⏳ <b>Заказ {order} ждёт оплаты</b>\n\n💰 Сумма: <b>{amount} сум</b>\n💳 Способ: {provider}\n\nЕсли оплата не поступит в течение {hours} ч, заказ будет отменён автоматически.",
        "en": "⏳ <b>Order {order} is waiting for payment</b>\n\n💰 Amount: <b>{amount} UZS</b>\n💳 Method: {provider}\n\nIf it isn't paid within {hours} h, the order is cancelled automatically.",
    },
    "pay": {"uz": "💳 {provider} orqali to'lash", "ru": "💳 Оплатить через {provider}", "en": "💳 Pay with {provider}"},
    "cash": {"uz": "💵 Naqd to'layman", "ru": "💵 Оплачу наличными", "en": "💵 I'll pay in cash"},
    "open": {"uz": "🌐 Buyurtmani ochish", "ru": "🌐 Открыть заказ", "en": "🌐 Open the order"},
}


def tr(key: str, lang: str, **kw) -> str:
    entry = TEXT[key]
    return entry.get(lang if lang in entry else "uz").format(**kw)


def money(v) -> str:
    return f"{int(v):,}".replace(",", " ")


# ---------------------------------------------------------------- what is "awaiting online payment"


@dataclass
class Awaiting:
    order: object
    latest: PaymentModel
    started_at: object  # first online attempt -- the clock for reminder and cancellation


def awaiting_orders():
    o = service._orders()
    online = PaymentModel.objects.exclude(provider="cash")
    order_ids = online.filter(status__in=service.OPEN_PAYMENT_STATUSES).values("order_id")
    paid = PaymentModel.objects.filter(status=PaymentStatusChoices.SUCCEEDED).values("order_id")
    orders = o.OrderModel.objects.filter(id__in=order_ids, status="pending_payment").exclude(id__in=paid)
    started = dict(online.filter(order_id__in=orders.values("id")).values("order_id").annotate(s=Min("created_at")).values_list("order_id", "s"))
    for order in orders:
        latest = online.filter(order_id=order.id).order_by("-created_at").first()
        if latest is None or latest.status not in service.OPEN_PAYMENT_STATUSES:
            continue  # the customer switched to cash (or the last attempt failed and they haven't retried)
        yield Awaiting(order=order, latest=latest, started_at=started.get(order.id, latest.created_at))


def in_flight_at_provider(order_id, now) -> bool:
    """A provider still holds an unfinished transaction (Payme/Uzum state 1, Click prepared) -- never cancel under it."""
    for p in PaymentModel.objects.filter(order_id=order_id, provider_state=1, status=PaymentStatusChoices.PENDING):
        if now - p.updated_at < PROVIDER_HOLD.get(p.provider, timedelta(hours=1)):
            return True
    return False


# ---------------------------------------------------------------- telegram


def pay_keyboard(order_number: str, method: str, checkout_url: str | None, lang: str) -> list:
    rows = []
    if checkout_url and checkout_url.startswith("https://"):
        rows.append([{"text": tr("pay", lang, provider=registry.provider_label(method)), "url": checkout_url}])
    rows.append([{"text": tr("cash", lang), "callback_data": f"pay:cash:{order_number}"}])
    base = (getattr(settings, "FRONTEND_URL", "") or "").rstrip("/")
    if base.startswith("https://"):
        rows.append([{"text": tr("open", lang), "url": f"{base}/orders/{order_number}"}])
    return rows


def send_pay_message(user, order, method: str, text: str) -> bool:
    """Telegram message with a direct link to the provider's payment page (returns to the bot afterwards)."""
    if not getattr(user, "telegram_user_id", None):
        return False
    lang = user.language if user.language in ("uz", "ru", "en") else "uz"
    url = None
    try:
        url = service.start_payment(order.customer_id, order.order_number, method, lang=lang, return_to=service.bot_return_url()).checkout_url
    except service.PaymentError as exc:
        logger.info("payment: no pay link for %s (%s)", order.order_number, exc.code)
    from apps.notifications.infrastructure import composition as notifications_composition

    notifications_composition.build_telegram_gateway().send_message_with_keyboard(str(user.telegram_user_id), text, pay_keyboard(order.order_number, method, url, lang))
    return True


# ---------------------------------------------------------------- jobs


def send_reminders(now=None) -> int:
    cfg = PaymentSettings.load()
    if not cfg.reminder_enabled:
        return 0
    now = now or timezone.now()
    from apps.identity.infrastructure.models import User
    from apps.notifications.infrastructure.notify import notify

    sent = 0
    for item in awaiting_orders():
        meta = item.latest.meta or {}
        if meta.get("reminded_at") or now - item.started_at < timedelta(minutes=cfg.reminder_after_minutes):
            continue
        # Never remind after the cancellation deadline would already have passed.
        if cfg.auto_cancel_enabled and now - item.started_at >= timedelta(hours=cfg.auto_cancel_after_hours):
            continue
        PaymentModel.objects.filter(pk=item.latest.pk).update(meta={**meta, "reminded_at": now.isoformat()})
        method = item.latest.method or item.latest.provider
        amount = money(service.payable(item.order))
        hours = cfg.auto_cancel_after_hours if cfg.auto_cancel_enabled else 0
        notify(item.order.customer_id, "payment_reminder", {"order": item.order.order_number, "amount": amount, "provider": registry.provider_label(method), "hours": hours},
               link=f"/orders/{item.order.order_number}", dedupe_key=f"payment_reminder:{item.order.id}", telegram=False)
        user = User.objects.filter(id=item.order.customer_id).only("telegram_user_id", "language").first()
        if user is not None:
            lang = user.language if user.language in ("uz", "ru", "en") else "uz"
            try:
                send_pay_message(user, item.order, method, tr("reminder", lang, order=item.order.order_number, amount=amount, provider=registry.provider_label(method), hours=hours))
            except Exception:  # noqa: BLE001 - Telegram trouble never stops the batch
                logger.exception("payment: reminder for %s not delivered to Telegram", item.order.order_number)
        sent += 1
    return sent


def cancel_expired(now=None) -> int:
    cfg = PaymentSettings.load()
    if not cfg.auto_cancel_enabled:
        return 0
    now = now or timezone.now()
    from apps.notifications.infrastructure.notify import notify
    from apps.ordering.application.services.lifecycle import CancelOrder
    from apps.ordering.infrastructure.composition import build_ordering_service_context
    from apps.ordering.infrastructure.repositories import DjangoOrderRepository

    cancelled = 0
    for item in list(awaiting_orders()):
        if now - item.started_at < timedelta(hours=cfg.auto_cancel_after_hours) or in_flight_at_provider(item.order.id, now):
            continue
        try:
            CancelOrder(DjangoOrderRepository(), build_ordering_service_context(actor_label="To'lov muddati")).execute(
                item.order.id, f"Onlayn to'lov {cfg.auto_cancel_after_hours} soat ichida amalga oshmadi"
            )
        except Exception:  # noqa: BLE001 - one bad order never blocks the rest
            logger.exception("payment: auto-cancel of %s failed", item.order.order_number)
            continue
        for p in PaymentModel.objects.filter(order_id=item.order.id, status__in=service.OPEN_PAYMENT_STATUSES):
            service.mark_cancelled(p, "Order auto-cancelled: unpaid")
        notify(item.order.customer_id, "order_payment_expired", {"order": item.order.order_number, "hours": cfg.auto_cancel_after_hours},
               link=f"/orders/{item.order.order_number}", dedupe_key=f"order_payment_expired:{item.order.id}")
        cancelled += 1
        logger.info("payment: order %s auto-cancelled (unpaid for %sh)", item.order.order_number, cfg.auto_cancel_after_hours)
    return cancelled


def choose_cash(customer_id, order_number: str) -> str:
    """The customer will pay the courier instead: closes the open online attempts. Returns ok / paid / not_found / not_open."""
    order = service.find_order(order_number)
    if order is None or order.customer_id != customer_id:
        return "not_found"
    if service.is_paid(order):
        return "paid"
    if order.status not in service.PAYABLE_ORDER_STATUSES:
        return "not_open"
    if in_flight_at_provider(order.id, timezone.now()):
        return "in_flight"
    for p in PaymentModel.objects.filter(order_id=order.id, status__in=service.OPEN_PAYMENT_STATUSES):
        service.mark_cancelled(p, "Customer chose cash on delivery")
    return "ok"
