"""
Online payment orchestration shared by every provider protocol (Payme / Click / Uzum):

- what an order costs (`payable`), whether it can be paid (`payability`),
- starting a payment from checkout (`start_payment` → provider checkout URL),
- the money moments: `mark_paid` (order gets a captured payment reference and, if it was waiting
  for payment, is confirmed -- stock reserved, customer notified), `mark_cancelled` / refunds,
- the callback journal (`log_callback`).

Protocol modules only translate their wire format into these calls; business rules live here once.
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone

from apps.payment.infrastructure.models import PaymentCallbackLog, PaymentModel, PaymentProviderConfig, PaymentStatusChoices
from apps.payment.infrastructure.providers import registry

logger = logging.getLogger("nutrizone.app")

PAYABLE_ORDER_STATUSES = ("pending_payment", "confirmed", "processing", "shipped")
OPEN_PAYMENT_STATUSES = (PaymentStatusChoices.CREATED, PaymentStatusChoices.PENDING)
REDACT_KEYS = {"key", "secret_key", "password", "sign_string", "authorization", "test_key"}


class PaymentError(Exception):
    """A business rejection with a stable code the storefront localises."""

    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------- orders


def _orders():
    from apps.ordering.infrastructure import models as ordering_orm

    return ordering_orm


def find_order(order_number: str):
    return _orders().OrderModel.objects.filter(order_number=str(order_number or "").strip()).first() if order_number else None


def payable(order) -> Decimal:
    """What the customer owes in so'm: active lines (unit × qty − discount + tax); coins/coupons already sit in the line discounts."""
    o = _orders()
    total = o.OrderLineItemModel.objects.filter(order_id=order.id, status="active").aggregate(
        t=Sum(ExpressionWrapper(F("unit_price_amount") * F("quantity") - F("discount_amount") + F("tax_amount"), output_field=DecimalField(max_digits=16, decimal_places=2)))
    )["t"]
    return (total or Decimal("0")).quantize(Decimal("0.01"))


CLOSED_ORDER_STATUSES = ("cancelled", "returned", "failed")


def order_closed(order_id) -> bool:
    """The order was cancelled/returned (e.g. auto-cancelled while unpaid): a late payment must be refused."""
    return _orders().OrderModel.objects.filter(id=order_id, status__in=CLOSED_ORDER_STATUSES).exists()


def is_paid(order) -> bool:
    return PaymentModel.objects.filter(order_id=order.id, status=PaymentStatusChoices.SUCCEEDED).exists()


def payability(order) -> str | None:
    """None when the order can be paid online now, else a reason code."""
    if order is None:
        return "ORDER_NOT_FOUND"
    if order.currency != "UZS":
        return "CURRENCY_NOT_SUPPORTED"
    if order.status not in PAYABLE_ORDER_STATUSES:
        return "ORDER_NOT_PAYABLE"
    if is_paid(order):
        return "ORDER_ALREADY_PAID"
    if payable(order) <= 0:
        return "ORDER_NOT_PAYABLE"
    return None


# ---------------------------------------------------------------- checkout


@dataclass
class StartedPayment:
    payment: PaymentModel
    checkout_url: str


def frontend_url() -> str:
    return (getattr(settings, "FRONTEND_URL", "") or "http://localhost:3000").rstrip("/")


def return_url(order_number: str) -> str:
    return f"{frontend_url()}/orders/{order_number}?payment=return"


def bot_return_url() -> str | None:
    """Back to the Telegram bot after paying (for orders placed / reminded in the bot)."""
    username = (getattr(settings, "TELEGRAM_BOT_USERNAME", "") or "").lstrip("@")
    return f"https://t.me/{username}" if username else None


def start_payment(customer_id, order_number: str, method: str, lang: str = "uz", return_to: str | None = None) -> StartedPayment:
    """Customer picked an online method for their order: one open payment per order+acquirer, and the provider's hosted page URL."""
    from apps.payment.infrastructure.providers import click, payme, uzum

    if method not in registry.SPECS or method == "cash":
        raise PaymentError("METHOD_NOT_AVAILABLE", "This payment method is not available.")
    state = registry.load(method)
    if state.status != "active":
        raise PaymentError("METHOD_NOT_AVAILABLE", "This payment method is not available.")
    order = find_order(order_number)
    if order is None or (customer_id and order.customer_id != customer_id):
        raise PaymentError("ORDER_NOT_FOUND", "Order not found.", status=404)
    reason = payability(order)
    if reason:
        raise PaymentError(reason, "This order can't be paid online.")
    amount = payable(order)
    acquirer = registry.acquirer_for(method)
    acq = registry.load(acquirer)
    if amount < acq.min_amount or (acq.max_amount and amount > acq.max_amount):
        raise PaymentError("AMOUNT_OUT_OF_RANGE", "The amount is outside this method's limits.")

    with transaction.atomic():
        # Another method's untouched attempt is dropped so only one provider can take the money.
        PaymentModel.objects.select_for_update().filter(order_id=order.id, status=PaymentStatusChoices.CREATED, provider_reference__isnull=True).exclude(provider=acquirer).update(
            status=PaymentStatusChoices.CANCELLED, cancelled_at=timezone.now(), failure_reason="switched method"
        )
        payment = PaymentModel.objects.filter(order_id=order.id, provider=acquirer, status__in=OPEN_PAYMENT_STATUSES, amount=amount).order_by("-created_at").first()
        if payment is None:
            payment = PaymentModel.objects.create(
                order_id=order.id, customer_id=order.customer_id or customer_id or uuid.UUID(int=0), amount=amount, currency="UZS",
                provider=acquirer, method=method, order_number=order.order_number, is_test=acq.test_mode,
            )
        elif payment.method != method:
            payment.method = method
            payment.save(update_fields=["method", "updated_at"])

    builder = {"payme": payme.checkout_url, "click": click.checkout_url, "uzum": uzum.checkout_url}[acquirer]
    return StartedPayment(payment=payment, checkout_url=builder(acq, order.order_number, amount, return_to or return_url(order.order_number), lang, method))


# ---------------------------------------------------------------- money moments


def mark_paid(payment: PaymentModel, label: str) -> None:
    """Payment captured: record it on the order and confirm an order that was waiting for payment. Idempotent."""
    from apps.ordering.application.services.lifecycle import ConfirmOrder
    from apps.ordering.domain.enums import OrderStatus, PaymentReferenceStatus
    from apps.ordering.infrastructure.composition import build_ordering_service_context
    from apps.ordering.infrastructure.repositories import DjangoOrderRepository
    from apps.ordering.domain.value_objects import Money

    with transaction.atomic():
        row = PaymentModel.objects.select_for_update().get(pk=payment.pk)
        if row.status == PaymentStatusChoices.SUCCEEDED:
            return
        row.status = PaymentStatusChoices.SUCCEEDED
        row.paid_at = timezone.now()
        row.save(update_fields=["status", "paid_at", "updated_at"])
        payment.status, payment.paid_at = row.status, row.paid_at

        repo = DjangoOrderRepository()
        order = repo.get_by_id(row.order_id)
        if order is None:
            logger.error("payment %s paid for a missing order %s", row.pk, row.order_id)
            return
        order.attach_payment_reference(row.id, Money(amount=row.amount, currency=row.currency))
        ref_id = next(ref_id for ref_id, ref in order.payment_references.items() if ref.payment_id == row.id)
        order.update_payment_status(ref_id, PaymentReferenceStatus.CAPTURED, row.paid_at)
        repo.save(order)
        if order.status == OrderStatus.PENDING_PAYMENT:
            ConfirmOrder(repo, build_ordering_service_context(actor_label=label)).execute(order.id)
        _notify(row, "payment_received")


def mark_cancelled(payment: PaymentModel, reason: str = "", refunded: bool = False) -> None:
    with transaction.atomic():
        row = PaymentModel.objects.select_for_update().get(pk=payment.pk)
        target = PaymentStatusChoices.REFUNDED if refunded else PaymentStatusChoices.CANCELLED
        if row.status == target:
            return
        was_paid = row.status == PaymentStatusChoices.SUCCEEDED
        row.status = target
        row.cancelled_at = timezone.now()
        row.failure_reason = (reason or "")[:255] or row.failure_reason
        row.save(update_fields=["status", "cancelled_at", "failure_reason", "updated_at"])
        payment.status, payment.cancelled_at = row.status, row.cancelled_at
        if was_paid:
            _mark_order_reference(row, refunded=True)
            _notify(row, "payment_refunded")


def _mark_order_reference(row: PaymentModel, refunded: bool) -> None:
    from apps.ordering.domain.enums import PaymentReferenceStatus
    from apps.ordering.infrastructure.repositories import DjangoOrderRepository

    repo = DjangoOrderRepository()
    order = repo.get_by_id(row.order_id)
    if order is None:
        return
    for ref_id, ref in order.payment_references.items():
        if ref.payment_id == row.id:
            order.update_payment_status(ref_id, PaymentReferenceStatus.REFUNDED if refunded else PaymentReferenceStatus.FAILED, timezone.now())
            repo.save(order)
            return


def _notify(row: PaymentModel, kind: str) -> None:
    from apps.notifications.infrastructure.notify import notify

    if not row.customer_id or row.customer_id == uuid.UUID(int=0):
        return
    notify(
        row.customer_id, kind,
        {"order": row.order_number, "amount": f"{int(row.amount):,}".replace(",", " "), "provider": registry.provider_label(row.method or row.provider)},
        link=f"/orders/{row.order_number}", dedupe_key=f"{kind}:{row.pk}",
    )


# ---------------------------------------------------------------- journal


def _redact(value):
    if isinstance(value, dict):
        return {k: ("•••" if k.lower() in REDACT_KEYS else _redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def log_callback(provider: str, method: str, request_data, response_data, *, payment: PaymentModel | None = None, order_number: str = "",
                 http_status: int = 200, error_code: int | None = None, ip: str | None = None, started: float | None = None) -> None:
    try:
        PaymentCallbackLog.objects.create(
            provider=provider, method=method[:48], payment=payment, order_number=(order_number or (payment.order_number if payment else ""))[:30],
            request=_redact(request_data) if isinstance(request_data, (dict, list)) else {"raw": str(request_data)[:2000]},
            response=_redact(response_data) if isinstance(response_data, (dict, list)) else {"raw": str(response_data)[:2000]},
            http_status=http_status, error_code=error_code, ip=ip, duration_ms=int((time.monotonic() - started) * 1000) if started else 0,
        )
        PaymentProviderConfig.objects.filter(provider=provider).update(last_callback_at=timezone.now())
    except Exception:  # noqa: BLE001 - the journal must never break a payment answer
        logger.exception("payment: could not write the callback journal")


def client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None
