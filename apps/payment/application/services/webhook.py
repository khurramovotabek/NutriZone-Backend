from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.ordering.domain.enums import PaymentReferenceStatus
from apps.payment.application.services._shared import PaymentServiceContext
from apps.payment.domain.aggregates import Payment
from apps.payment.domain.events import PaymentAudited
from apps.payment.domain.exceptions import PaymentAmountMismatch, PaymentNotFound
from apps.payment.infrastructure.repositories import DjangoPaymentRepository


def _find_reference_id(order, payment_id: uuid.UUID) -> uuid.UUID:
    """Order.update_payment_status() keys on OrderPaymentReference's own internal id, not Payment.id -- these are two separate UUIDs (confirmed by reading Order.attach_payment_reference(), which generates a fresh uuid.uuid4() for the reference itself). Reused from the same fix already applied in CreatePayment."""
    from common.exceptions import ResourceNotFound

    for ref_id, ref in order.payment_references.items():
        if ref.payment_id == payment_id:
            return ref_id
    raise ResourceNotFound("Payment reference not found on order.")


class ProcessPaymentCallback:
    """
    Handles an async provider callback/webhook. The trust boundary is
    provider-authentication + provider_reference (never a
    client-supplied payment_id/order_id/customer_id) -- callers must
    authenticate the provider before this service is ever invoked
    (see the webhook view). Reported amount/currency are compared
    against this Payment's own authoritative, already-stored values;
    a mismatch is rejected, never used to redefine the Payment.
    """

    def __init__(self, payment_repo: DjangoPaymentRepository, order_repo, ctx: PaymentServiceContext) -> None:
        self._payment_repo = payment_repo
        self._order_repo = order_repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, provider_reference: str, reported_status: str, reported_amount: Decimal, reported_currency: str) -> Payment:
        payment = self._payment_repo.get_by_provider_reference(provider_reference)
        if payment is None:
            raise PaymentNotFound("No payment found for this provider reference.")

        if payment.status.value in ("succeeded", "failed", "cancelled"):
            return payment

        if reported_amount != payment.amount.amount or reported_currency != payment.amount.currency:
            raise PaymentAmountMismatch(f"Callback reported {reported_amount} {reported_currency}, expected {payment.amount.amount} {payment.amount.currency}.")

        from apps.ordering.infrastructure import composition as ordering_composition

        order = self._order_repo.get_by_id(payment.order_id)
        reference_id = _find_reference_id(order, payment.id)

        if reported_status == "succeeded":
            event = payment.mark_succeeded(django_timezone.now())
            self._payment_repo.save(payment)
            self._ctx.stage_events([("PaymentSucceeded", event.to_payload())])
            ordering_composition.build_update_payment_status(payment.customer_id).execute(order_id=payment.order_id, payment_reference_id=reference_id, status=PaymentReferenceStatus.CAPTURED)
            audit_event = PaymentAudited(payment_id=payment.id, action="webhook_success", before_status="pending", after_status="succeeded")
            self._ctx.stage_events([("PaymentAudited", audit_event.to_payload())])
        elif reported_status == "failed":
            event = payment.mark_failed("Provider callback reported failure.", django_timezone.now())
            self._payment_repo.save(payment)
            self._ctx.stage_events([("PaymentFailed", event.to_payload())])
            ordering_composition.build_update_payment_status(payment.customer_id).execute(order_id=payment.order_id, payment_reference_id=reference_id, status=PaymentReferenceStatus.FAILED)
            audit_event = PaymentAudited(payment_id=payment.id, action="webhook_failure", before_status="pending", after_status="failed")
            self._ctx.stage_events([("PaymentAudited", audit_event.to_payload())])

        return payment
