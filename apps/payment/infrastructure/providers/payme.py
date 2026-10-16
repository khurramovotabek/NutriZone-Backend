"""
Payme Merchant API (JSON-RPC 2.0) -- https://developer.help.paycom.uz

Payme calls ONE endpoint (POST /api/v1/payments/payme) with Basic auth "Paycom:<key>" and a method:
CheckPerformTransaction, CreateTransaction, PerformTransaction, CancelTransaction, CheckTransaction,
GetStatement, SetFiscalData. With "Payme orqali fiskal chek" on (Chek sozlamalari) CheckPerformTransaction also returns
the fiscal `detail` (MXIK, package code, VAT per line) and SetFiscalData stores the tax receipt (apps/receipts/payme_fiscal). Amounts are tiyin (1 so'm = 100). Transaction states: 1 created, 2 performed,
-1 cancelled before perform, -2 cancelled after perform (refund). A created transaction expires
after 12 hours (cancel reason 4).

The account field (order number) is the one configured in the Payme cabinet ("order_id" by default).
"""
from __future__ import annotations

import base64
import hmac
from decimal import Decimal

from django.db import transaction

from apps.payment.infrastructure import service
from apps.payment.infrastructure.models import PaymentModel, PaymentStatusChoices
from apps.payment.infrastructure.providers.registry import ProviderState, load

TIMEOUT_MS = 12 * 60 * 60 * 1000
CHECKOUT_URL = "https://checkout.paycom.uz"
CHECKOUT_URL_TEST = "https://checkout.test.paycom.uz"

# Error codes from the Merchant API reference.
ERR_AUTH = -32504
ERR_METHOD = -32601
ERR_PARSE = -32700
ERR_POST = -32300
ERR_SERVER = -32400
ERR_AMOUNT = -31001
ERR_NOT_FOUND = -31003
ERR_CANT_CANCEL = -31007
ERR_CANT_PERFORM = -31008
ERR_ORDER = -31050  # -31050..-31099: problems with the account (order)
ERR_ORDER_PAID = -31051
ERR_ORDER_BUSY = -31052
ERR_RECEIPT_NOT_FOUND = -32001  # SetFiscalData: no transaction with this id
ERR_PARAMS = -32602

MESSAGES = {
    ERR_AUTH: ("Недостаточно привилегий", "Ruxsat yo'q", "Insufficient privileges"),
    ERR_METHOD: ("Метод не найден", "Metod topilmadi", "Method not found"),
    ERR_PARSE: ("Ошибка разбора JSON", "JSON xato", "JSON parse error"),
    ERR_POST: ("Метод запроса должен быть POST", "So'rov POST bo'lishi kerak", "Request method must be POST"),
    ERR_SERVER: ("Системная ошибка", "Tizim xatosi", "System error"),
    ERR_AMOUNT: ("Неверная сумма", "Noto'g'ri summa", "Incorrect amount"),
    ERR_NOT_FOUND: ("Транзакция не найдена", "Tranzaksiya topilmadi", "Transaction not found"),
    ERR_CANT_CANCEL: ("Заказ выполнен, отмена невозможна", "Buyurtma bajarilgan, bekor qilib bo'lmaydi", "Order fulfilled, can't cancel"),
    ERR_CANT_PERFORM: ("Невозможно выполнить операцию", "Amalni bajarib bo'lmaydi", "Unable to perform operation"),
    ERR_ORDER: ("Заказ не найден", "Buyurtma topilmadi", "Order not found"),
    ERR_ORDER_PAID: ("Заказ уже оплачен или не может быть оплачен", "Buyurtma to'langan yoki to'lab bo'lmaydi", "Order already paid or not payable"),
    ERR_RECEIPT_NOT_FOUND: ("Чек не найден", "Chek topilmadi", "Receipt not found"),
    ERR_PARAMS: ("Неверные параметры", "Noto'g'ri parametrlar", "Invalid parameters"),
    ERR_ORDER_BUSY: ("Заказ ожидает оплаты по другой транзакции", "Buyurtma boshqa tranzaksiya bilan to'lanmoqda", "Order is being paid by another transaction"),
}


class PaymeError(Exception):
    def __init__(self, code: int, data: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.data = data


def tiyin(amount: Decimal) -> int:
    return int((Decimal(amount) * 100).quantize(Decimal("1")))


def checkout_url(state: ProviderState, order_number: str, amount: Decimal, return_to: str, lang: str = "uz", method: str = "payme") -> str:
    lang = lang if lang in ("uz", "ru", "en") else "uz"
    params = f"m={state.value('merchant_id')};ac.{state.value('account_field')}={order_number};a={tiyin(amount)};c={return_to};l={lang}"
    base = CHECKOUT_URL_TEST if state.test_mode else CHECKOUT_URL
    return f"{base}/{base64.b64encode(params.encode()).decode()}"


def authorised(state: ProviderState, header: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        login, _, password = base64.b64decode(header[6:]).decode().partition(":")
    except (ValueError, UnicodeDecodeError):
        return False
    key = state.value("test_key") if state.test_mode else state.value("key")
    return bool(key) and login == "Paycom" and hmac.compare_digest(password, key)


def error(request_id, code: int, data: str | None = None) -> dict:
    ru, uz, en = MESSAGES.get(code, MESSAGES[ERR_SERVER])
    body = {"code": code, "message": {"ru": ru, "uz": uz, "en": en}}
    if data:
        body["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": body}


# ---------------------------------------------------------------- dispatcher


def handle(payload: dict, auth_header: str) -> tuple[dict, PaymentModel | None, str]:
    """Returns (JSON-RPC response, payment it concerned, order number) -- the view logs all three."""
    state = load("payme")
    request_id = payload.get("id") if isinstance(payload, dict) else None
    if not authorised(state, auth_header or ""):
        return error(request_id, ERR_AUTH), None, ""
    if not isinstance(payload, dict) or "method" not in payload:
        return error(request_id, ERR_PARSE), None, ""
    params = payload.get("params") or {}
    handler = HANDLERS.get(payload["method"])
    if handler is None:
        return error(request_id, ERR_METHOD, payload.get("method")), None, ""
    ctx: dict = {"payment": None, "order": ""}
    try:
        result = handler(state, params, ctx)
    except PaymeError as exc:
        return error(request_id, exc.code, exc.data), ctx["payment"], ctx["order"]
    return {"jsonrpc": "2.0", "id": request_id, "result": result}, ctx["payment"], ctx["order"]


def _account_order(state: ProviderState, params: dict, ctx: dict):
    account = params.get("account") or {}
    field = state.value("account_field") or "order_id"
    number = account.get(field) or account.get("order_id")
    ctx["order"] = str(number or "")
    order = service.find_order(number)
    if order is None:
        raise PaymeError(ERR_ORDER, field)
    return order


def _validate(state: ProviderState, params: dict, ctx: dict):
    order = _account_order(state, params, ctx)
    reason = service.payability(order)
    if reason == "ORDER_NOT_FOUND":
        raise PaymeError(ERR_ORDER, "order_id")
    if reason:
        raise PaymeError(ERR_ORDER_PAID, "order_id")
    try:
        amount = int(params.get("amount"))
    except (TypeError, ValueError):
        raise PaymeError(ERR_AMOUNT) from None
    if amount != tiyin(service.payable(order)):
        raise PaymeError(ERR_AMOUNT)
    return order, amount


def _by_txn(params: dict, ctx: dict, lock: bool = False) -> PaymentModel:
    txn_id = str(params.get("id") or "")
    qs = PaymentModel.objects.select_for_update() if lock else PaymentModel.objects
    payment = qs.filter(provider="payme", provider_reference=f"payme:{txn_id}").first() if txn_id else None
    if payment is None:
        raise PaymeError(ERR_NOT_FOUND)
    ctx["payment"], ctx["order"] = payment, payment.order_number
    return payment


def _txn_view(p: PaymentModel) -> dict:
    return {
        "create_time": p.provider_created_at or 0, "perform_time": p.provider_performed_at or 0, "cancel_time": p.provider_cancelled_at or 0,
        "transaction": str(p.pk), "state": p.provider_state, "reason": p.cancel_reason,
    }


def _expire(p: PaymentModel) -> None:
    p.provider_state, p.cancel_reason, p.provider_cancelled_at = -1, 4, service.now_ms()
    p.save(update_fields=["provider_state", "cancel_reason", "provider_cancelled_at", "updated_at"])
    service.mark_cancelled(p, "Payme: transaction timed out")


# ---------------------------------------------------------------- methods


def check_perform(state: ProviderState, params: dict, ctx: dict) -> dict:
    order, amount = _validate(state, params, ctx)
    from apps.receipts.infrastructure import payme_fiscal

    if payme_fiscal.enabled():
        detail = payme_fiscal.detail(order, amount)
        if detail:
            return {"allow": True, "detail": detail}
    return {"allow": True}


def set_fiscal_data(state: ProviderState, params: dict, ctx: dict) -> dict:
    """Payme reports the tax receipt its virtual kassa registered for a payment (PERFORM) or its refund (CANCEL)."""
    kind, data = params.get("type"), params.get("fiscal_data")
    if kind not in ("PERFORM", "CANCEL"):
        raise PaymeError(ERR_PARAMS, "type")
    if not isinstance(data, dict):
        raise PaymeError(ERR_PARAMS, "fiscal_data")
    try:
        payment = _by_txn(params, ctx)
    except PaymeError:
        raise PaymeError(ERR_RECEIPT_NOT_FOUND, "id") from None
    from apps.receipts.infrastructure import payme_fiscal

    payme_fiscal.save_fiscal_data(payment, kind, data)
    return {"success": True}


def _expire_if_stale(p: PaymentModel) -> bool:
    """Cancels (reason 4) a created transaction older than 12 h -- committed on its own, so the cancellation
    survives the error answer that follows."""
    if p.provider_state != 1 or service.now_ms() - (p.provider_created_at or 0) <= TIMEOUT_MS:
        return False
    with transaction.atomic():
        fresh = PaymentModel.objects.select_for_update().get(pk=p.pk)
        if fresh.provider_state == 1:
            _expire(fresh)
    return True


def create_transaction(state: ProviderState, params: dict, ctx: dict) -> dict:
    txn_id = str(params.get("id") or "")
    existing = PaymentModel.objects.filter(provider="payme", provider_reference=f"payme:{txn_id}").first()
    if existing is not None:
        ctx["payment"], ctx["order"] = existing, existing.order_number
        if _expire_if_stale(existing) or existing.provider_state != 1:
            raise PaymeError(ERR_CANT_PERFORM)
        return {"create_time": existing.provider_created_at, "transaction": str(existing.pk), "state": 1}

    order, _amount = _validate(state, params, ctx)
    for stale in PaymentModel.objects.filter(order_id=order.id, provider="payme", provider_state=1):
        _expire_if_stale(stale)

    with transaction.atomic():
        twin = PaymentModel.objects.select_for_update().filter(provider="payme", provider_reference=f"payme:{txn_id}").first()
        if twin is not None:  # a concurrent duplicate of this same CreateTransaction won the race: answer like a retry
            ctx["payment"] = twin
            return {"create_time": twin.provider_created_at, "transaction": str(twin.pk), "state": twin.provider_state}
        if PaymentModel.objects.select_for_update().filter(order_id=order.id, provider="payme", provider_state=1).exists():
            raise PaymeError(ERR_ORDER_BUSY, "order_id")

        # Reuse the attempt checkout created (no provider id yet), else open one -- e.g. paid from the Payme app directly.
        payment = PaymentModel.objects.select_for_update().filter(
            order_id=order.id, provider="payme", provider_reference__isnull=True, status__in=service.OPEN_PAYMENT_STATUSES
        ).order_by("-created_at").first()
        if payment is None:
            payment = PaymentModel(order_id=order.id, customer_id=order.customer_id, currency="UZS", provider="payme", method="payme", order_number=order.order_number)
        payment.amount = service.payable(order)
        payment.provider_reference = f"payme:{txn_id}"
        payment.status = PaymentStatusChoices.PENDING
        payment.provider_state = 1
        payment.provider_created_at = service.now_ms()
        payment.is_test = state.test_mode
        payment.meta = {**(payment.meta or {}), "payme_time": params.get("time")}
        payment.save()
        ctx["payment"] = payment
        return {"create_time": payment.provider_created_at, "transaction": str(payment.pk), "state": 1}


def perform_transaction(state: ProviderState, params: dict, ctx: dict) -> dict:
    if _expire_if_stale(_by_txn(params, ctx)):
        raise PaymeError(ERR_CANT_PERFORM)
    with transaction.atomic():
        p = _by_txn(params, ctx, lock=True)
        if p.provider_state == 2:
            return {"transaction": str(p.pk), "perform_time": p.provider_performed_at, "state": 2}
        if p.provider_state != 1 or service.order_closed(p.order_id):
            raise PaymeError(ERR_CANT_PERFORM)
        p.provider_state, p.provider_performed_at = 2, service.now_ms()
        p.save(update_fields=["provider_state", "provider_performed_at", "updated_at"])
        service.mark_paid(p, "Payme")
        return {"transaction": str(p.pk), "perform_time": p.provider_performed_at, "state": 2}


def cancel_transaction(state: ProviderState, params: dict, ctx: dict) -> dict:
    with transaction.atomic():
        p = _by_txn(params, ctx, lock=True)
        if p.provider_state in (-1, -2):
            return {"transaction": str(p.pk), "cancel_time": p.provider_cancelled_at, "state": p.provider_state}
        reason = params.get("reason")
        if p.provider_state == 2:
            # A refund: refused once the goods are on their way or delivered.
            order = service._orders().OrderModel.objects.filter(id=p.order_id).values_list("status", flat=True).first()
            if order in ("shipped", "delivered", "completed"):
                raise PaymeError(ERR_CANT_CANCEL)
            p.provider_state = -2
        else:
            p.provider_state = -1
        p.cancel_reason = int(reason) if isinstance(reason, int) else None
        p.provider_cancelled_at = service.now_ms()
        p.save(update_fields=["provider_state", "cancel_reason", "provider_cancelled_at", "updated_at"])
        service.mark_cancelled(p, f"Payme cancel, reason {reason}", refunded=p.provider_state == -2)
        return {"transaction": str(p.pk), "cancel_time": p.provider_cancelled_at, "state": p.provider_state}


def check_transaction(state: ProviderState, params: dict, ctx: dict) -> dict:
    return _txn_view(_by_txn(params, ctx))


def get_statement(state: ProviderState, params: dict, ctx: dict) -> dict:
    try:
        start, end = int(params.get("from")), int(params.get("to"))
    except (TypeError, ValueError):
        raise PaymeError(ERR_SERVER, "from/to") from None
    field = state.value("account_field") or "order_id"
    rows = PaymentModel.objects.filter(provider="payme", provider_created_at__gte=start, provider_created_at__lte=end).order_by("provider_created_at")
    return {"transactions": [
        {
            "id": p.provider_reference.split(":", 1)[1], "time": (p.meta or {}).get("payme_time") or p.provider_created_at, "amount": tiyin(p.amount),
            "account": {field: p.order_number}, "receivers": None, **_txn_view(p),
        }
        for p in rows if p.provider_reference
    ]}


HANDLERS = {
    "CheckPerformTransaction": check_perform,
    "CreateTransaction": create_transaction,
    "PerformTransaction": perform_transaction,
    "CancelTransaction": cancel_transaction,
    "CheckTransaction": check_transaction,
    "GetStatement": get_statement,
    "SetFiscalData": set_fiscal_data,
}
