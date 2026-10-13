"""
Click SHOP API -- https://docs.click.uz/click-api-request/

Click calls two URLs set in the merchant cabinet (merchant.click.uz), form-encoded POST:
  Prepare  (action=0)  → we check the order and amount, answer merchant_prepare_id
  Complete (action=1)  → Click reports the result; error < 0 means the payment failed at Click
Every request is signed:
  md5(click_trans_id + service_id + SECRET_KEY + merchant_trans_id [+ merchant_prepare_id] + amount + action + sign_time)
merchant_trans_id is our order number. Amounts are so'm (may carry decimals, e.g. "150000.00").
"""
from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.db import IntegrityError, transaction

from apps.payment.infrastructure import service
from apps.payment.infrastructure.models import PaymentModel, PaymentStatusChoices
from apps.payment.infrastructure.providers.registry import ProviderState, load

CHECKOUT_URL = "https://my.click.uz/services/pay"

OK = 0
ERR_SIGN = -1
ERR_AMOUNT = -2
ERR_ACTION = -3
ERR_ALREADY_PAID = -4
ERR_ORDER = -5
ERR_TXN = -6
ERR_UPDATE = -7
ERR_REQUEST = -8
ERR_CANCELLED = -9

NOTES = {
    OK: "Success", ERR_SIGN: "SIGN CHECK FAILED!", ERR_AMOUNT: "Incorrect parameter amount", ERR_ACTION: "Action not found",
    ERR_ALREADY_PAID: "Already paid", ERR_ORDER: "User does not exist", ERR_TXN: "Transaction does not exist",
    ERR_UPDATE: "Failed to update user", ERR_REQUEST: "Error in request from click", ERR_CANCELLED: "Transaction cancelled",
}
REQUIRED = ("click_trans_id", "service_id", "merchant_trans_id", "amount", "action", "sign_time", "sign_string")


def checkout_url(state: ProviderState, order_number: str, amount: Decimal, return_to: str, lang: str = "uz", method: str = "click") -> str:
    query = {
        "service_id": state.value("service_id"), "merchant_id": state.value("merchant_id"), "amount": f"{Decimal(amount):.2f}",
        "transaction_param": order_number, "return_url": return_to,
    }
    if method in ("uzcard", "humo"):
        query["card_type"] = method
    return f"{CHECKOUT_URL}?{urlencode(query)}"


def signature(state: ProviderState, data: dict, with_prepare_id: bool) -> str:
    parts = [str(data.get("click_trans_id", "")), str(data.get("service_id", "")), state.value("secret_key"), str(data.get("merchant_trans_id", ""))]
    if with_prepare_id:
        parts.append(str(data.get("merchant_prepare_id", "")))
    parts += [str(data.get("amount", "")), str(data.get("action", "")), str(data.get("sign_time", ""))]
    return hashlib.md5("".join(parts).encode()).hexdigest()  # noqa: S324 - md5 is Click's documented signature


def _answer(data: dict, code: int, **extra) -> dict:
    return {"click_trans_id": data.get("click_trans_id"), "merchant_trans_id": data.get("merchant_trans_id"), **extra, "error": code, "error_note": NOTES.get(code, "Error")}


def _common(state: ProviderState, data: dict, action: int, with_prepare_id: bool):
    """Shared Prepare/Complete checks. Returns (error_code or None, order, amount)."""
    if any(data.get(k) in (None, "") for k in REQUIRED) or (with_prepare_id and not data.get("merchant_prepare_id")):
        return ERR_REQUEST, None, None
    if not state.value("secret_key") or not hmac.compare_digest(signature(state, data, with_prepare_id), str(data.get("sign_string", "")).lower()):
        return ERR_SIGN, None, None
    if str(data.get("service_id")) != str(state.value("service_id")):
        return ERR_REQUEST, None, None
    if str(data.get("action")) != str(action):
        return ERR_ACTION, None, None
    try:
        amount = Decimal(str(data.get("amount")))
    except InvalidOperation:
        return ERR_AMOUNT, None, None
    order = service.find_order(data.get("merchant_trans_id"))
    if order is None:
        return ERR_ORDER, None, amount
    return None, order, amount


def prepare(data: dict) -> tuple[dict, PaymentModel | None]:
    state = load("click")
    code, order, amount = _common(state, data, 0, with_prepare_id=False)
    if code is not None:
        return _answer(data, code), None
    reason = service.payability(order)
    if reason == "ORDER_ALREADY_PAID":
        return _answer(data, ERR_ALREADY_PAID), None
    if reason:
        return _answer(data, ERR_ORDER), None
    if amount != service.payable(order):
        return _answer(data, ERR_AMOUNT), None

    ref = f"click:{data['click_trans_id']}"
    try:
        with transaction.atomic():
            payment = PaymentModel.objects.select_for_update().filter(provider_reference=ref).first()
            if payment is None:
                payment = PaymentModel.objects.select_for_update().filter(
                    order_id=order.id, provider="click", provider_reference__isnull=True, status__in=service.OPEN_PAYMENT_STATUSES
                ).order_by("-created_at").first() or PaymentModel(
                    order_id=order.id, customer_id=order.customer_id, currency="UZS", provider="click", method="click", order_number=order.order_number,
                )
                payment.provider_reference = ref
                payment.amount = amount
                payment.status = PaymentStatusChoices.PENDING
                payment.provider_state = 1
                payment.is_test = state.test_mode
                payment.meta = {**(payment.meta or {}), "click_paydoc_id": data.get("click_paydoc_id")}
                payment.save()
            elif payment.status == PaymentStatusChoices.CANCELLED:
                return _answer(data, ERR_CANCELLED), payment
            if payment.prepare_id is None:
                # A short, unique integer Click echoes back in Complete.
                payment.prepare_id = int(payment.created_at.timestamp() * 1000) % 10**12 * 10 + (payment.pk.int % 10)
                payment.save(update_fields=["prepare_id", "updated_at"])
    except IntegrityError:
        return _answer(data, ERR_UPDATE), None
    return _answer(data, OK, merchant_prepare_id=payment.prepare_id), payment


def complete(data: dict) -> tuple[dict, PaymentModel | None]:
    state = load("click")
    code, order, amount = _common(state, data, 1, with_prepare_id=True)
    if code is not None and code != ERR_ORDER:
        return _answer(data, code), None
    try:
        prepare_id = int(data.get("merchant_prepare_id"))
    except (TypeError, ValueError):
        return _answer(data, ERR_REQUEST), None
    with transaction.atomic():
        payment = PaymentModel.objects.select_for_update().filter(provider="click", prepare_id=prepare_id, provider_reference=f"click:{data['click_trans_id']}").first()
        if payment is None:
            return _answer(data, ERR_TXN), None
        if payment.status == PaymentStatusChoices.SUCCEEDED:
            return _answer(data, ERR_ALREADY_PAID, merchant_confirm_id=payment.prepare_id), payment
        if payment.status == PaymentStatusChoices.CANCELLED:
            return _answer(data, ERR_CANCELLED), payment
        if amount != payment.amount:
            return _answer(data, ERR_AMOUNT), payment
        try:
            click_error = int(data.get("error") or 0)
        except (TypeError, ValueError):
            click_error = 0
        if click_error < 0:
            # The payment failed on Click's side (insufficient funds, card declined ...).
            payment.provider_state = -1
            payment.save(update_fields=["provider_state", "updated_at"])
            service.mark_cancelled(payment, f"Click: {data.get('error_note') or click_error}")
            return _answer(data, ERR_CANCELLED), payment
        if order is None or service.payability(order) not in (None,):
            # Order vanished or got cancelled between Prepare and Complete -- refuse; Click reverses the charge.
            payment.provider_state = -1
            payment.save(update_fields=["provider_state", "updated_at"])
            service.mark_cancelled(payment, "Click: order no longer payable")
            return _answer(data, ERR_ORDER if order is None else ERR_CANCELLED), payment
        payment.provider_state = 2
        payment.provider_performed_at = service.now_ms()
        payment.save(update_fields=["provider_state", "provider_performed_at", "updated_at"])
        service.mark_paid(payment, "Click")
        return _answer(data, OK, merchant_confirm_id=payment.prepare_id), payment
