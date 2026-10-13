from __future__ import annotations

import uuid

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.payment.infrastructure import composition
from apps.payment.interfaces.api.v1.permissions import CanCreatePayment
from apps.payment.interfaces.api.v1.serializers import CreatePaymentSerializer, PaymentWebhookSerializer
from common.idempotency import protect_with_idempotency
from common.responses import error_response

# Phase 10b: closes a real, confirmed gap in the existing shared
# idempotency infrastructure -- its DB-level uniqueness constraint is
# (created_by, operation_scope, key), and PostgreSQL's NULL != NULL
# semantics mean actor_id=None provides NO real uniqueness guarantee
# at all (confirmed via a real failing test: two same-key requests
# with actor_id=None both inserted successfully). A webhook is
# genuinely actor-less (no customer JWT), so a fixed, deterministic
# non-null pseudo-actor is used here instead -- scoped narrowly to
# this one operation, not a change to the shared infrastructure.
_WEBHOOK_PSEUDO_ACTOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _attach_identity(request) -> None:
    request.identity = request.user


def _actor_id(request):
    return getattr(getattr(request, "user", None), "id", None)


def _payment_payload(payment) -> dict:
    return {
        "id": str(payment.id), "order_id": str(payment.order_id), "status": payment.status.value,
        "amount": str(payment.amount.amount), "currency": payment.amount.currency, "provider": payment.provider,
        "provider_reference": payment.provider_reference, "failure_reason": payment.failure_reason,
    }


class CreatePaymentView(APIView):
    """
    Phase 10: the new, customer-safe payment-creation endpoint.
    Accepts only order_id/provider -- the authoritative amount is
    computed entirely server-side by CreatePayment from the Order's
    own real, already-certified line items. Protected by this
    project's existing, proven idempotency mechanism
    (protect_with_idempotency) -- no new idempotency system.
    """

    def get_permissions(self):
        return [CanCreatePayment()]

    @extend_schema(tags=["Payment"], summary="Create a payment attempt for an order (server-authoritative amount, no client price accepted)", request=CreatePaymentSerializer, responses={201: OpenApiResponse(description="Payment created"), 403: OpenApiResponse(description="Forbidden"), 404: OpenApiResponse(description="Order not found"), 409: OpenApiResponse(description="Conflict"), 422: OpenApiResponse(description="Validation error")})
    def post(self, request):
        _attach_identity(request)
        serializer = CreatePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor_id = _actor_id(request)

        return protect_with_idempotency(
            request, actor_id, "payment.create", serializer.validated_data,
            operation=lambda: composition.build_create_payment().execute(order_id=serializer.validated_data["order_id"], customer_id=actor_id, provider=serializer.validated_data["provider"]),
            result_to_payload=_payment_payload,
            success_status_code=201,
        )


class PaymentWebhookView(APIView):
    """
    Phase 10b: the machine-to-machine payment callback endpoint. The
    trust boundary here is deliberately NOT customer authentication --
    it is provider authentication (WebhookAuthenticator) plus
    provider_reference resolution inside ProcessPaymentCallback
    itself (never a caller-chosen payment_id/order_id/customer_id).
    No real provider is configured (confirmed absent), so
    WebhookAuthenticator defaults to NotConfiguredWebhookAuthenticator,
    which always rejects -- honest, not fabricated. Protected by the
    same existing idempotency mechanism as every other financial
    mutation in this project; the caller (whatever forwards the
    provider's webhook) must send a real Idempotency-Key header --
    a real provider's own event/transaction ID is a reasonable choice.
    """

    permission_classes = [AllowAny]  # webhook trust boundary is provider auth, not customer JWT -- enforced explicitly below, not by DRF permission classes

    @extend_schema(tags=["Payment"], summary="Process a payment provider webhook/callback (provider-authenticated, not customer-authenticated)", request=PaymentWebhookSerializer, responses={200: OpenApiResponse(description="Processed"), 401: OpenApiResponse(description="Provider authentication failed"), 404: OpenApiResponse(description="Unknown payment"), 409: OpenApiResponse(description="Amount/currency mismatch or conflict"), 422: OpenApiResponse(description="Validation error")})
    def post(self, request):
        authenticator = composition.build_webhook_authenticator()
        if not authenticator.verify(dict(request.headers), request.body):
            return error_response(code="INVALID_SIGNATURE", message="Webhook authentication failed.", category="authentication", status_code=401)

        serializer = PaymentWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        return protect_with_idempotency(
            request, _WEBHOOK_PSEUDO_ACTOR_ID, "payment.webhook", {"provider_reference": data["provider_reference"], "status": data["status"], "amount": str(data["amount"]), "currency": data["currency"]},
            operation=lambda: composition.build_process_payment_callback().execute(
                provider_reference=data["provider_reference"], reported_status=data["status"], reported_amount=data["amount"], reported_currency=data["currency"],
            ),
            result_to_payload=_payment_payload,
            success_status_code=200,
        )
