"""
Uzum Bank Merchant API -- the bank calls us (Basic auth login:password, JSON POST) under one base URL:

  /check    {serviceId, timestamp, params}                 → is this order payable?   status OK
  /create   {serviceId, timestamp, transId, params, amount} → hold a transaction       status CREATED
  /confirm  {serviceId, timestamp, transId, ...}           → money captured           status CONFIRMED
  /reverse  {serviceId, timestamp, transId}                → cancelled / refunded     status REVERSED
  /status   {serviceId, timestamp, transId}                → current state

Amounts are tiyin. Failures answer HTTP 400 {status: "FAILED", errorCode} -- codes and the exact semantics below
follow Uzum's published Merchant API spec (developer.uzumbank.uz/en/merchant, en_merchant.yaml, checked 2026-11-16):

  * a repeated /create with the same transId → 10010, a repeated /confirm → 10016, a repeated /reverse → 10018
    (Uzum retries a timed-out /confirm through /status, not by repeating it);
  * /confirm of a cancelled transaction → 10015; a /reverse we can't honour → 10017;
  * a transaction not confirmed within 30 minutes of /create is FAILED (we expire it, the order stays payable);
  * min / max amount from the dashboard limits → 10012 / 10013.

The order number travels in params[<key>] -- "order_id" by default, the key is set in the dashboard to whatever
Uzum configured for the service ("account" in their examples); answers echo it back as data[<key>].value.
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

ERR_AUTH = "10001"           # access denied
ERR_JSON = "10002"           # JSON parsing error
ERR_OPERATION = "10003"      # invalid operation (method)
ERR_PARAMS = "10005"         # missing required parameters
ERR_SERVICE = "10006"        # invalid serviceId
ERR_ORDER = "10007"          # additional payment attribute (order) not found
ERR_ALREADY_PAID = "10008"   # payment already made
ERR_CANCELLED = "10009"      # payment (order) cancelled
ERR_TXN_EXISTS = "10010"     # transaction with this transId already created
ERR_AMOUNT = "10011"         # invalid amount
ERR_AMOUNT_MIN = "10012"     # below the minimum
ERR_AMOUNT_MAX = "10013"     # above the maximum
ERR_TXN = "10014"            # transaction not found
ERR_TXN_CANCELLED = "10015"  # cancelled transaction can't be confirmed
ERR_TXN_CONFIRMED = "10016"  # already confirmed
ERR_CANT_REVERSE = "10017"   # can't be cancelled in its current state
ERR_TXN_REVERSED = "10018"   # already cancelled
ERR_INTERNAL = "99999"
ERR_NOT_PAYABLE = ERR_CANCELLED  # kept for callers: an order that can't take money any more
CONFIRM_TIMEOUT_MS = 30 * 60 * 1000

MESSAGES = {
    ERR_AUTH: "Ruxsat yo'q (login/parol)", ERR_JSON: "JSON xato", ERR_OPERATION: "Noto'g'ri amal", ERR_PARAMS: "Majburiy parametr yo'q",
    ERR_SERVICE: "Noto'g'ri serviceId", ERR_ORDER: "Buyurtma topilmadi", ERR_ALREADY_PAID: "Buyurtma allaqachon to'langan", ERR_CANCELLED: "Buyurtmani to'lab bo'lmaydi",
    ERR_TXN_EXISTS: "Tranzaksiya allaqachon yaratilgan", ERR_AMOUNT: "Summa mos emas", ERR_AMOUNT_MIN: "Summa minimaldan kam", ERR_AMOUNT_MAX: "Summa maksimaldan ko'p",
    ERR_TXN: "Tranzaksiya topilmadi", ERR_TXN_CANCELLED: "Tranzaksiya bekor qilingan", ERR_TXN_CONFIRMED: "Tranzaksiya allaqachon tasdiqlangan",
    ERR_CANT_REVERSE: "Tranzaksiyani bekor qilib bo'lmaydi", ERR_TXN_REVERSED: "Tranzaksiya allaqachon bekor qilingan", ERR_INTERNAL: "Ichki xato",
}


def param_key(state: ProviderState) -> str:
    return (state.value("param_key") or ORDER_PARAM).strip() or ORDER_PARAM


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
        "status": status or _status_name(p), "amount": tiyin(p.amount), "data": {param_key(state): {"value": p.order_number}}, **extra,
    }


def handle(action: str, data: dict, auth_header: str) -> tuple[dict, PaymentModel | None, str, int]:
    """Returns (answer, payment, order number, http status)."""
    state = load("uzum")
    if not authorised(state, auth_header or ""):
        return _fail(state, ERR_AUTH, data if isinstance(data, dict) else None), None, "", 401
    if not isinstance(data, dict):
        return _fail(state, ERR_JSON), None, "", 400
    handler = HANDLERS.get(action)
    if handler is None:
        return _fail(state, ERR_OPERATION, data), None, "", 400
    if data.get("serviceId") in (None, "") or data.get("timestamp") in (None, "") or (action != "check" and not data.get("transId")):
        return _fail(state, ERR_PARAMS, data), None, "", 400
    if str(data.get("serviceId")) != str(state.value("service_id")):
        return _fail(state, ERR_SERVICE, data), None, "", 400
    answer, payment, order = handler(state, data)
    return answer, payment, order, 200 if answer.get("status") != "FAILED" else 400


def _order_from_params(state: ProviderState, data: dict):
    params = data.get("params") or {}
    number = params.get(param_key(state)) or params.get(ORDER_PARAM) or params.get("account")
    return service.find_order(str(number) if number not in (None, "") else None), str(number or "")


def _check_order(state: ProviderState, order, amount: int | None):
    if order is None:
        return ERR_ORDER
    reason = service.payability(order)
    if reason == "ORDER_ALREADY_PAID":
        return ERR_ALREADY_PAID
    if reason:
        return ERR_CANCELLED
    if amount is not None:
        if state.min_amount and amount < tiyin(state.min_amount):
            return ERR_AMOUNT_MIN
        if state.max_amount and amount > tiyin(state.max_amount):
            return ERR_AMOUNT_MAX
        if amount != tiyin(service.payable(order)):
            return ERR_AMOUNT
    return None


def _expire_if_stale(p: PaymentModel) -> bool:
    """A created transaction Uzum didn't confirm within 30 minutes is FAILED (spec) -- the order stays payable."""
    if p.provider_state != 1 or service.now_ms() - (p.provider_created_at or 0) <= CONFIRM_TIMEOUT_MS:
        return False
    with transaction.atomic():
        fresh = PaymentModel.objects.select_for_update().get(pk=p.pk)
        if fresh.provider_state == 1:
            fresh.provider_state, fresh.provider_cancelled_at = -1, service.now_ms()
            fresh.save(update_fields=["provider_state", "provider_cancelled_at", "updated_at"])
            service.mark_cancelled(fresh, "Uzum Bank: not confirmed within 30 minutes")
    return True


def check(state: ProviderState, data: dict):
    order, number = _order_from_params(state, data)
    code = _check_order(state, order, None)
    if code:
        return _fail(state, code, data), None, number
    info = {param_key(state): {"value": order.order_number}, "amount": {"value": str(tiyin(service.payable(order)))}}
    return {"serviceId": _service_id(state, data), "timestamp": service.now_ms(), "status": "OK", "data": info}, None, number


def create(state: ProviderState, data: dict):
    trans_id = str(data.get("transId") or "")
    if not trans_id:
        return _fail(state, ERR_PARAMS, data), None, ""
    ref = f"uzum:{trans_id}"
    existing = PaymentModel.objects.filter(provider_reference=ref).first()
    if existing is not None:
        return _fail(state, ERR_TXN_EXISTS, data), existing, existing.order_number
    order, number = _order_from_params(state, data)
    try:
        amount = int(data.get("amount"))
    except (TypeError, ValueError):
        return _fail(state, ERR_PARAMS, data), None, number
    code = _check_order(state, order, amount)
    if code:
        return _fail(state, code, data), None, number
    for stale in PaymentModel.objects.filter(order_id=order.id, provider="uzum", provider_state=1):
        _expire_if_stale(stale)
    try:
        with transaction.atomic():
            if PaymentModel.objects.select_for_update().filter(order_id=order.id, provider="uzum", provider_state=1).exists():
                return _fail(state, ERR_CANCELLED, data), None, number  # another transaction for this order is in flight
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
    except IntegrityError:  # a concurrent duplicate of the same /create won
        payment = PaymentModel.objects.get(provider_reference=ref)
        return _fail(state, ERR_TXN_EXISTS, data), payment, number
    return _view(state, payment, transTime=payment.provider_created_at), payment, number


def _by_trans(data: dict) -> PaymentModel | None:
    trans_id = str(data.get("transId") or "")
    return PaymentModel.objects.filter(provider="uzum", provider_reference=f"uzum:{trans_id}").first() if trans_id else None


def confirm(state: ProviderState, data: dict):
    p = _by_trans(data)
    if p is None:
        return _fail(state, ERR_TXN, data), None, ""
    if _expire_if_stale(p):
        return _fail(state, ERR_TXN_CANCELLED, data), p, p.order_number
    with transaction.atomic():
        p = PaymentModel.objects.select_for_update().get(pk=p.pk)
        if p.provider_state == 2:
            return _fail(state, ERR_TXN_CONFIRMED, data), p, p.order_number
        if p.provider_state != 1 or service.order_closed(p.order_id):
            return _fail(state, ERR_TXN_CANCELLED, data), p, p.order_number
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
            return _fail(state, ERR_TXN_REVERSED, data), p, p.order_number
        refund = p.provider_state == 2
        if refund:
            status = service._orders().OrderModel.objects.filter(id=p.order_id).values_list("status", flat=True).first()
            if status in ("shipped", "delivered", "completed"):
                return _fail(state, ERR_CANT_REVERSE, data), p, p.order_number
        p.provider_state = -2 if refund else -1
        p.provider_cancelled_at = service.now_ms()
        p.save(update_fields=["provider_state", "provider_cancelled_at", "updated_at"])
        service.mark_cancelled(p, "Uzum Bank: reversed", refunded=refund)
    return _view(state, p, reverseTime=p.provider_cancelled_at), p, p.order_number


def status(state: ProviderState, data: dict):
    p = _by_trans(data)
    if p is None:
        return _fail(state, ERR_TXN, data), None, ""
    _expire_if_stale(p)
    p.refresh_from_db()
    return _view(state, p, transTime=p.provider_created_at, confirmTime=p.provider_performed_at, reverseTime=p.provider_cancelled_at), p, p.order_number


HANDLERS = {"check": check, "create": create, "confirm": confirm, "reverse": reverse, "status": status}
