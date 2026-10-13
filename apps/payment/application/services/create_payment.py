from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.ordering.domain.enums import OrderStatus, PaymentReferenceStatus
from apps.payment.application.gateway import PaymentGateway
from apps.payment.application.services._shared import PaymentServiceContext
from apps.payment.domain.aggregates import Payment
from apps.payment.domain.exceptions import OrderNotPayable
from apps.payment.domain.value_objects import PaymentAmount
from apps.payment.infrastructure.repositories import DjangoPaymentRepository
from common.exceptions import PermissionDenied, ResourceNotFound


def compute_order_payable_amount(order) -> Decimal:
    """
    The one authoritative source for what an Order is payable for --
    a real, direct sum of the Order's own already-certified line
    items (unit_price * quantity - discount + tax, for ACTIVE lines
    only). This is arithmetic on already-server-priced data, not a
    new pricing formula: every component value here was already
    computed and persisted by CreateOrderFromCart from the cart's own
    real PriceSnapshot chain (Phase 09.4-09.7). No Order.total field
    exists on the aggregate (confirmed by direct search) -- this
    mirrors the same safe, display-only-sum pattern already
    established and proven in CheckoutPreviewView (Phase 09.5).
    """
    total = Decimal("0")
    for line in order.lines.values():
        if line.status.value != "active":
            continue
        total += (line.unit_price.amount * line.quantity) - line.discount_amount.amount + line.tax_amount.amount
    return total


class CreatePayment:
    """
    Phase 10: the real payment-creation composition this project was
    missing. Never accepts amount/currency/total from the caller --
    only order_id, provider, and the actor performing the request.
    """

    def __init__(self, order_repo, payment_repo: DjangoPaymentRepository, gateway: PaymentGateway, ctx: PaymentServiceContext) -> None:
        self._order_repo = order_repo
        self._payment_repo = payment_repo
        self._gateway = gateway
        self._ctx = ctx

    def execute(self, order_id: uuid.UUID, customer_id: uuid.UUID, provider: str) -> Payment:
        order = self._order_repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")
        if order.customer_id != customer_id:
            raise PermissionDenied("This order does not belong to you.")
        if order.status != OrderStatus.PENDING_PAYMENT:
            raise OrderNotPayable(f"Order is in status {order.status.value}, not payable.")

        payable_amount = compute_order_payable_amount(order)
        if payable_amount <= 0:
            raise OrderNotPayable("Order has no payable amount.")
        amount = PaymentAmount(amount=payable_amount, currency=order.currency)

        with transaction.atomic():
            from apps.ordering.infrastructure import composition as ordering_composition

            payment_id = uuid.uuid4()
            payment, created_event = Payment.create(payment_id=payment_id, order_id=order_id, customer_id=customer_id, amount=amount, provider=provider, at=django_timezone.now())
            self._payment_repo.save(payment)
            self._ctx.stage_events([("PaymentCreated", created_event.to_payload())])

            ordering_composition.build_attach_payment_reference(customer_id).execute(order_id=order_id, payment_id=payment_id, amount=amount.amount)

            charge = self._gateway.create_charge(amount=amount.amount, currency=amount.currency, order_reference=str(order_id), idempotency_key=str(payment_id))

            if charge.status == "succeeded":
                payment.mark_pending(charge.provider_reference, django_timezone.now())
                succeeded_event = payment.mark_succeeded(django_timezone.now())
                self._payment_repo.save(payment)
                self._ctx.stage_events([("PaymentSucceeded", succeeded_event.to_payload())])

                order_payment_ref_id = self._find_reference_id(order_id, payment_id)
                ordering_composition.build_update_payment_status(customer_id).execute(order_id=order_id, payment_reference_id=order_payment_ref_id, status=PaymentReferenceStatus.CAPTURED)
            elif charge.status == "pending":
                payment.mark_pending(charge.provider_reference, django_timezone.now())
                self._payment_repo.save(payment)
            else:
                failed_event = payment.mark_failed("Gateway reported failure at creation.", django_timezone.now())
                self._payment_repo.save(payment)
                self._ctx.stage_events([("PaymentFailed", failed_event.to_payload())])
                order_payment_ref_id = self._find_reference_id(order_id, payment_id)
                ordering_composition.build_update_payment_status(customer_id).execute(order_id=order_id, payment_reference_id=order_payment_ref_id, status=PaymentReferenceStatus.FAILED)

        return payment

    def _find_reference_id(self, order_id: uuid.UUID, payment_id: uuid.UUID) -> uuid.UUID:
        order = self._order_repo.get_by_id(order_id)
        for ref_id, ref in order.payment_references.items():
            if ref.payment_id == payment_id:
                return ref_id
        raise ResourceNotFound("Payment reference not found on order.")
