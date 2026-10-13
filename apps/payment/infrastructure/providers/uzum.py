"""
Uzum Bank Merchant API -- the bank calls us (Basic auth login:password, JSON POST) under one base URL:

  /check    {serviceId, timestamp, params}                 → is this order payable?   status OK
  /create   {serviceId, timestamp, transId, params, amount} → hold a transaction       status CREATED
  /confirm  {serviceId, timestamp, transId, ...}           → money captured           status CONFIRMED
  /reverse  {serviceId, timestamp, transId}                → cancelled / refunded     status REVERSED
  /status   {serviceId, timestamp, transId}                → current state

Amounts are tiyin. Failures answer {status: "FAILED", errorCode}. The order number travels in
params[<field>] ("order_id"). Error codes follow Uzum's Merchant API reference -- confirm the list
against the documentation Uzum sends with the contract during onboarding (the dashboard journal
shows every request/answer to make that check easy).
"""
from __future__ import annotations

import base64
import hmac
from decimal import Decimal

from django.db import IntegrityError, transaction

from apps.payment.infrastructure import service
from apps.payment.infrastructure.models import PaymentModel, PaymentStatusChoices
from apps.payment.infrastructure.providers.registry import ProviderState, load

ORDER_PARAM = "order_id"

ERR_AUTH = "10001"
ERR_JSON = "10002"
ERR_OPERATION = "10003"
ERR_PARAMS = "10005"
ERR_SERVICE = "10006"
ERR_ORDER = "10007"
ERR_ALREADY_PAID = "10008"
ERR_CANCELLED = "10009"
ERR_AMOUNT = "10011"
ERR_TXN = "10014"
ERR_NOT_PAYABLE = "10017"


def tiyin(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def checkout_url(state: ProviderState, order_number: str, amount: Decimal, return_to: str, lang: str = "uz", method: str = "uzum") -> str:
    template = state.value("checkout_url")
    return template.format(service_id=state.value("service_id"), order=order_number, amount=tiyin(amount), return_url=return_to, lang=lang)


def authorised(state: ProviderState, header: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        login, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    return bool(state.value("password")) and hmac.compare_digest(login, state.value("login")) and hmac.compare_digest(password, state.value("password"))


def _fail(state: ProviderState, code: str, data: dict | None = None) -> dict:
    out = {"serviceId": _service_id(state, data), "timestamp": service.now_ms(), "status": "FAILED", "errorCode": code}
    if data and data.get("transId"):
        out["transId"] = data["transId"]
    return out


def _service_id(state: ProviderState, data: dict | None):
    try:
        return int(state.value("service_id"))
    except (TypeError, ValueError):
        return (data or {}).get("serviceId")


def _status_name(p: PaymentModel) -> str:
    return {1: "CREATED", 2: "CONFIRMED", -1: "REVERSED", -2: "REVERSED"}.get(p.provider_state, "FAILED")


def _view(state: ProviderState, p: PaymentModel, status: str | None = None, **extra) -> dict:
    return {
        "serviceId": _service_id(state, None), "transId": p.provider_reference.split(":", 1)[1] if p.provider_reference else None,
        "status": status or _status_name(p), "amount": tiyin(p.amount), "data": {ORDER_PARAM: {"value": p.order_number}}, **extra,
    }


def handle(action: str, data: dict, auth_header: str) -> tuple[dict, PaymentModel | None, str, int]:
    """Returns (answer, payment, order number, http status)."""
    state = load("uzum")
    if not authorised(state, auth_header or ""):
        return _fail(state, ERR_AUTH, data if isinstance(data, dict) else None), None, "", 401
    if not isinstance(data, dict):
        return _fail(state, ERR_JSON), None, "", 400
    if str(data.get("serviceId")) != str(state.value("service_id")):
        return _fail(state, ERR_SERVICE, data), None, "", 400
    handler = HANDLERS.get(action)
    if handler is None:
        return _fail(state, ERR_OPERATION, data), None, "", 400
    answer, payment, order = handler(state, data)
    return answer, payment, order, 200 if answer.get("status") != "FAILED" else 400


def _order_from_params(data: dict):
    params = data.get("params") or {}
    number = params.get(ORDER_PARAM) or params.get("account")
    return service.find_order(number), str(number or "")


def _check_order(state: ProviderState, order, amount: int | None):
    if order is None:
        return ERR_ORDER
    reason = service.payability(order)
    if reason == "ORDER_ALREADY_PAID":
        return ERR_ALREADY_PAID
    if reason:
        return ERR_NOT_PAYABLE
    if amount is not None and amount != tiyin(service.payable(order)):
        return ERR_AMOUNT
    return None


def check(state: ProviderState, data: dict):
    order, number = _order_from_params(data)
    code = _check_order(state, order, None)
    if code:
        return _fail(state, code, data), None, number
    return {"serviceId": _service_id(state, data), "timestamp": service.now_ms(), "status": "OK", "data": {ORDER_PARAM: {"value": order.order_number}}}, None, number


def create(state: ProviderState, data: dict):
    trans_id = str(data.get("transId") or "")
    if not trans_id:
        return _fail(state, ERR_PARAMS, data), None, ""
    ref = f"uzum:{trans_id}"
    existing = PaymentModel.objects.filter(provider_reference=ref).first()
    if existing is not None:
        return _view(state, existing, transTime=existing.provider_created_at), existing, existing.order_number
    order, number = _order_from_params(data)
    try:
        amount = int(data.get("amount"))
    except (TypeError, ValueError):
        return _fail(state, ERR_PARAMS, data), None, number
    code = _check_order(state, order, amount)
    if code:
        return _fail(state, code, data), None, number
    try:
        with transaction.atomic():
            if PaymentModel.objects.select_for_update().filter(order_id=order.id, provider="uzum", provider_state=1).exists():
                return _fail(state, ERR_NOT_PAYABLE, data), None, number
            payment = PaymentModel.objects.select_for_update().filter(
                order_id=order.id, provider="uzum", provider_reference__isnull=True, status__in=service.OPEN_PAYMENT_STATUSES
            ).order_by("-created_at").first() or PaymentModel(
                order_id=order.id, customer_id=order.customer_id, currency="UZS", provider="uzum", method="uzum", order_number=order.order_number,
            )
            payment.provider_reference = ref
            payment.amount = service.payable(order)
            payment.status = PaymentStatusChoices.PENDING
            payment.provider_state = 1
            payment.provider_created_at = service.now_ms()
            payment.is_test = state.test_mode
            payment.save()
    except IntegrityError:
        payment = PaymentModel.objects.get(provider_reference=ref)
    return _view(state, payment, transTime=payment.provider_created_at), payment, number


def _by_trans(data: dict) -> PaymentModel | None:
    trans_id = str(data.get("transId") or "")
    return PaymentModel.objects.filter(provider="uzum", provider_reference=f"uzum:{trans_id}").first() if trans_id else None


def confirm(state: ProviderState, data: dict):
    p = _by_trans(data)
    if p is None:
        return _fail(state, ERR_TXN, data), None, ""
    with transaction.atomic():
        p = PaymentModel.objects.select_for_update().get(pk=p.pk)
        if p.provider_state == 2:
            return _view(state, p, confirmTime=p.provider_performed_at), p, p.order_number
        if p.provider_state != 1 or service.order_closed(p.order_id):
            return _fail(state, ERR_CANCELLED, data), p, p.order_number
        p.provider_state, p.provider_performed_at = 2, service.now_ms()
        p.meta = {**(p.meta or {}), "paymentSource": data.get("paymentSource"), "processingReferenceNumber": data.get("processingReferenceNumber")}
        p.save(update_fields=["provider_state", "provider_performed_at", "meta", "updated_at"])
        service.mark_paid(p, "Uzum Bank")
    return _view(state, p, confirmTime=p.provider_performed_at), p, p.order_number


def reverse(state: ProviderState, data: dict):
    p = _by_trans(data)
    if p is None:
        return _fail(state, ERR_TXN, data), None, ""
    with transaction.atomic():
        p = PaymentModel.objects.select_for_update().get(pk=p.pk)
        if p.provider_state in (-1, -2):
            return _view(state, p, reverseTime=p.provider_cancelled_at), p, p.order_number
        refund = p.provider_state == 2
        if refund:
            status = service._orders().OrderModel.objects.filter(id=p.order_id).values_list("status", flat=True).first()
            if status in ("shipped", "delivered", "completed"):
                return _fail(state, ERR_OPERATION, data), p, p.order_number
        p.provider_state = -2 if refund else -1
        p.provider_cancelled_at = service.now_ms()
        p.save(update_fields=["provider_state", "provider_cancelled_at", "updated_at"])
        service.mark_cancelled(p, "Uzum Bank: reversed", refunded=refund)
    return _view(state, p, reverseTime=p.provider_cancelled_at), p, p.order_number


def status(state: ProviderState, data: dict):
    p = _by_trans(data)
    if p is None:
        return _fail(state, ERR_TXN, data), None, ""
    return _view(state, p, transTime=p.provider_created_at, confirmTime=p.provider_performed_at, reverseTime=p.provider_cancelled_at), p, p.order_number


HANDLERS = {"check": check, "create": create, "confirm": confirm, "reverse": reverse, "status": status}
