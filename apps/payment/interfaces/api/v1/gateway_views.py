"""
Online acquiring endpoints.

Storefront (customer JWT):
  GET  /payments/methods                      every method with its availability (coming soon when off)
  POST /payments/orders/<number>/pay {method}  → provider checkout URL for the customer's order
  GET  /payments/orders/<number>               → is it paid / can it still be paid online

Provider callbacks (no JWT -- each protocol authenticates the caller itself):
  POST /payments/payme                         Payme Merchant API (JSON-RPC, Basic auth)
  POST /payments/click/prepare | complete      Click SHOP API (form, md5 signature)
  POST /payments/uzum/<action>                 Uzum Bank Merchant API (JSON, Basic auth)

Every callback request/answer lands in the dashboard's callback journal.
"""
from __future__ import annotations

import json
import time

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.identity.interfaces.api.v1.permissions import IsAuthenticatedIdentityUser
from apps.payment.infrastructure import service
from apps.payment.infrastructure.models import PaymentModel
from apps.payment.infrastructure.providers import click, payme, registry, uzum
from common.responses import error_response, success_response


def method_payload(state: registry.ProviderState) -> dict:
    status = state.status
    return {
        "key": state.key, "name": str(state.spec.name), "color": state.spec.color, "online": state.spec.online,
        "available": status == "active", "status": "active" if status == "active" else "coming_soon",
        "test_mode": bool(state.test_mode and state.spec.online and status == "active"),
        "min_amount": str(state.min_amount) if state.spec.online else None, "max_amount": str(state.max_amount) if state.max_amount else None,
        "via": state.route if state.key in registry.CARD_BRANDS else None,
    }


class PaymentMethodsView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(tags=["Payment"], summary="Payment methods for checkout (unavailable ones are 'coming_soon')", responses={200: OpenApiResponse(description="Methods")})
    def get(self, request):
        return success_response(data=[method_payload(s) for s in registry.all_states()])


class OrderPaymentView(APIView):
    permission_classes = [IsAuthenticatedIdentityUser]

    def _order(self, request, number):
        order = service.find_order(number)
        return order if order is not None and order.customer_id == request.user.id else None

    @extend_schema(tags=["Payment"], summary="Online payment state of my order", responses={200: OpenApiResponse(description="State")})
    def get(self, request, number: str):
        order = self._order(request, number)
        if order is None:
            return error_response("ORDER_NOT_FOUND", "Order not found.", "business", 404)
        latest = PaymentModel.objects.filter(order_id=order.id).exclude(provider="cash").order_by("-created_at").first()
        reason = service.payability(order)
        return success_response(data={
            "order_number": order.order_number, "paid": service.is_paid(order), "amount": str(service.payable(order)),
            "can_pay_online": reason is None and any(m["available"] and m["online"] for m in (method_payload(s) for s in registry.all_states())),
            "latest": {"status": latest.status, "method": latest.method or latest.provider, "provider": latest.provider,
                       "paid_at": latest.paid_at.isoformat() if latest.paid_at else None} if latest else None,
        })

    @extend_schema(tags=["Payment"], summary="Start paying my order online → checkout URL", responses={200: OpenApiResponse(description="Checkout URL"), 409: OpenApiResponse(description="Not payable")})
    def post(self, request, number: str):
        method = str(request.data.get("method") or "")
        lang = str(request.data.get("lang") or "uz")
        try:
            started = service.start_payment(request.user.id, number, method, lang=lang)
        except service.PaymentError as exc:
            return error_response(exc.code, str(exc), "conflict" if exc.status == 409 else "business", exc.status)
        return success_response(data={"checkout_url": started.checkout_url, "payment_id": str(started.payment.pk), "provider": started.payment.provider, "method": method})


# ---------------------------------------------------------------- provider callbacks


@method_decorator(csrf_exempt, name="dispatch")
class PaymeCallbackView(View):
    def post(self, request):
        started = time.monotonic()
        try:
            payload = json.loads(request.body or b"{}")
        except ValueError:
            answer = payme.error(None, payme.ERR_PARSE)
            service.log_callback("payme", "parse_error", {"raw": request.body[:2000].decode(errors="replace")}, answer, error_code=payme.ERR_PARSE, ip=service.client_ip(request), started=started)
            return JsonResponse(answer)
        answer, payment, order = payme.handle(payload, request.headers.get("Authorization", ""))
        err = (answer.get("error") or {}).get("code")
        service.log_callback("payme", str(payload.get("method", "?")) if isinstance(payload, dict) else "?", payload, answer,
                             payment=payment, order_number=order, error_code=err, ip=service.client_ip(request), started=started)
        return JsonResponse(answer)

    def get(self, request):
        return JsonResponse(payme.error(None, payme.ERR_POST))


@method_decorator(csrf_exempt, name="dispatch")
class ClickCallbackView(View):
    action = "prepare"

    def post(self, request):
        started = time.monotonic()
        data = request.POST.dict() if request.POST else _json_or_empty(request.body)
        answer, payment = (click.prepare if self.action == "prepare" else click.complete)(data)
        service.log_callback("click", self.action, data, answer, payment=payment, order_number=str(data.get("merchant_trans_id") or ""),
                             error_code=answer.get("error"), ip=service.client_ip(request), started=started)
        return JsonResponse(answer)


@method_decorator(csrf_exempt, name="dispatch")
class UzumCallbackView(View):
    def post(self, request, action: str):
        started = time.monotonic()
        data = _json_or_empty(request.body, strict=True)
        answer, payment, order, status = uzum.handle(action, data, request.headers.get("Authorization", ""))
        code = answer.get("errorCode")
        service.log_callback("uzum", action, data if isinstance(data, dict) else {"raw": str(request.body[:2000])}, answer, payment=payment,
                             order_number=order, http_status=status, error_code=int(code) if code else None, ip=service.client_ip(request), started=started)
        return JsonResponse(answer, status=status)


def _json_or_empty(raw: bytes, strict: bool = False):
    try:
        return json.loads(raw or b"{}")
    except ValueError:
        return None if strict else {}


