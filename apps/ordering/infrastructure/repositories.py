"""
Ordering repositories.

Concrete implementations of application/ports.py's Protocols -- maps
ORM rows to domain dataclasses only, never leaks ORM objects outside
this module, matching the pattern established by every prior module.
`OrderInvoice` and `AddressSnapshot` are embedded as flat columns on
OrderModel (both are singular, at-most-one-per-order pieces of data,
not genuine collections), mirroring the same design choice already
made for Cart's shipping/tax estimates.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from django.db import IntegrityError

from apps.ordering.domain.aggregates import Order, OrderCancellation, OrderReturn
from apps.ordering.domain.entities import (
    CancellationLineItem, OrderFailure, OrderFulfillmentReference, OrderInvoice, OrderLineItem,
    OrderPaymentReference, OrderStatusHistoryEntry, ReturnLineItem,
)
from apps.ordering.domain.enums import (
    CancellationReason, CancellationStatus, FulfillmentReferenceStatus, InvoiceStatus, OrderChannel,
    OrderFailureReason, OrderLineItemStatus, OrderLockReason, OrderStatus, OrderType, PaymentReferenceStatus,
    ReturnReason, ReturnStatus,
)
from apps.ordering.domain.value_objects import AddressSnapshot, CustomerComment, Money, OrderNote, OrderNumber, OrderVersion, ReturnNumber, TrackingNumber
from apps.ordering.infrastructure import models as orm
from common.exceptions import ConflictError


def _address_from_row(row, prefix: str) -> AddressSnapshot:
    return AddressSnapshot(
        recipient_name=getattr(row, f"{prefix}_recipient_name"), line1=getattr(row, f"{prefix}_line1"), line2=getattr(row, f"{prefix}_line2"),
        city=getattr(row, f"{prefix}_city"), region=getattr(row, f"{prefix}_region"), postal_code=getattr(row, f"{prefix}_postal_code"),
        country_code=getattr(row, f"{prefix}_country_code"), phone=getattr(row, f"{prefix}_phone"),
        latitude=getattr(row, f"{prefix}_latitude"), longitude=getattr(row, f"{prefix}_longitude"),
    )


def _address_to_fields(address: AddressSnapshot, prefix: str) -> dict:
    return {
        f"{prefix}_recipient_name": address.recipient_name, f"{prefix}_line1": address.line1, f"{prefix}_line2": address.line2,
        f"{prefix}_city": address.city, f"{prefix}_region": address.region, f"{prefix}_postal_code": address.postal_code,
        f"{prefix}_country_code": address.country_code, f"{prefix}_phone": address.phone,
        f"{prefix}_latitude": address.latitude, f"{prefix}_longitude": address.longitude,
    }


class DjangoOrderRepository:
    def get_by_id(self, order_id: uuid.UUID) -> Order | None:
        row = orm.OrderModel.objects.filter(id=order_id).prefetch_related("lines", "payment_references", "fulfillment_references", "failures", "status_history").first()
        return self._to_domain(row) if row else None

    def get_by_order_number(self, order_number: str) -> Order | None:
        row = orm.OrderModel.objects.filter(order_number=order_number).prefetch_related("lines", "payment_references", "fulfillment_references", "failures", "status_history").first()
        return self._to_domain(row) if row else None

    def get_by_cart_id(self, cart_id: uuid.UUID) -> Order | None:
        row = orm.OrderModel.objects.filter(cart_id=cart_id).prefetch_related("lines", "payment_references", "fulfillment_references", "failures", "status_history").first()
        return self._to_domain(row) if row else None

    def save(self, order: Order) -> Order:
        try:
            row, _ = orm.OrderModel.objects.update_or_create(
                id=order.id,
                defaults={
                    "order_number": order.order_number.value, "customer_id": order.customer_id, "cart_id": order.cart_id, "currency": order.currency,
                    "order_type": order.order_type.value, "channel": order.channel.value, "status": order.status.value, "version": order.version.value,
                    "lock_reason": order.lock_reason.value if order.lock_reason else None, "is_archived": order.is_archived,
                    "coupon_ids": [str(c) for c in order.coupon_ids], "promotion_ids": [str(p) for p in order.promotion_ids],
                    "note": order.note.text if order.note else None, "customer_comment": order.customer_comment.text if order.customer_comment else None,
                    "placed_at": order.placed_at,
                    **_address_to_fields(order.shipping_address, "shipping"), **_address_to_fields(order.billing_address, "billing"),
                    "invoice_id": order.invoice.id if order.invoice else None, "invoice_number": order.invoice.invoice_number if order.invoice else None,
                    "invoice_total_amount": order.invoice.total_amount.amount if order.invoice else None, "invoice_status": order.invoice.status.value if order.invoice else None,
                    "invoice_issued_at": order.invoice.issued_at if order.invoice else None,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("An order with conflicting unique fields already exists.") from exc

        existing_line_ids = set(row.lines.values_list("id", flat=True))
        for line in order.lines.values():
            orm.OrderLineItemModel.objects.update_or_create(
                id=line.id,
                defaults={
                    "order": row, "product_variant_id": line.product_variant_id, "quantity": line.quantity, "unit_price_amount": line.unit_price.amount,
                    "discount_amount": line.discount_amount.amount, "tax_amount": line.tax_amount.amount, "status": line.status.value,
                    "price_snapshot_id": line.price_snapshot_id, "reservation_id": line.reservation_id,
                },
            )
        stale_line_ids = existing_line_ids - set(order.lines.keys())
        if stale_line_ids:
            orm.OrderLineItemModel.objects.filter(id__in=stale_line_ids).delete()

        existing_payment_ref_ids = set(row.payment_references.values_list("id", flat=True))
        for ref in order.payment_references.values():
            if ref.id not in existing_payment_ref_ids:
                orm.OrderPaymentReferenceModel.objects.create(id=ref.id, order=row, payment_id=ref.payment_id, amount=ref.amount.amount, currency=ref.amount.currency, status=ref.status.value, processed_at=ref.processed_at)
            else:
                orm.OrderPaymentReferenceModel.objects.filter(id=ref.id).update(status=ref.status.value, processed_at=ref.processed_at)

        existing_fulfillment_ref_ids = set(row.fulfillment_references.values_list("id", flat=True))
        for ref in order.fulfillment_references.values():
            if ref.id not in existing_fulfillment_ref_ids:
                orm.OrderFulfillmentReferenceModel.objects.create(id=ref.id, order=row, fulfillment_id=ref.fulfillment_id, status=ref.status.value, tracking_number=ref.tracking_number.value if ref.tracking_number else None, shipped_at=ref.shipped_at, delivered_at=ref.delivered_at)
            else:
                orm.OrderFulfillmentReferenceModel.objects.filter(id=ref.id).update(status=ref.status.value, tracking_number=ref.tracking_number.value if ref.tracking_number else None, shipped_at=ref.shipped_at, delivered_at=ref.delivered_at)

        existing_failure_ids = set(row.failures.values_list("id", flat=True))
        for failure in order.failures:
            if failure.id not in existing_failure_ids:
                orm.OrderFailureModel.objects.create(id=failure.id, order=row, reason=failure.reason.value, detail=failure.detail, occurred_at=failure.occurred_at)

        existing_history_ids = set(row.status_history.values_list("id", flat=True))
        for entry in order.status_history:
            if entry.id not in existing_history_ids:
                orm.OrderStatusHistoryEntryModel.objects.create(id=entry.id, order=row, from_status=entry.from_status, to_status=entry.to_status, reason=entry.reason, changed_at=entry.changed_at, actor_id=entry.actor_id)

        return order

    def list_for_customer(self, customer_id: uuid.UUID, status: str | None, page: int, page_size: int) -> tuple[list[Order], int]:
        qs = orm.OrderModel.objects.filter(customer_id=customer_id)
        if status:
            qs = qs.filter(status=status)
        total = qs.count()
        rows = qs.order_by("-created_at")[(page - 1) * page_size : page * page_size]
        return [self.get_by_id(r.id) for r in rows], total

    def list_expiring_before(self, at: datetime) -> list[Order]:
        rows = orm.OrderModel.objects.filter(status__in=[OrderStatus.DRAFT.value, OrderStatus.PENDING_PAYMENT.value], placed_at__isnull=False, placed_at__lte=at)
        return [self.get_by_id(r.id) for r in rows]

    def list_for_admin(self, status: str | None, page: int, page_size: int) -> tuple[list[Order], int]:
        qs = orm.OrderModel.objects.all()
        if status:
            qs = qs.filter(status=status)
        total = qs.count()
        rows = qs.order_by("-created_at")[(page - 1) * page_size : page * page_size]
        return [self.get_by_id(r.id) for r in rows], total

    def _to_domain(self, row: orm.OrderModel) -> Order:
        lines = {
            l.id: OrderLineItem(
                id=l.id, product_variant_id=l.product_variant_id, quantity=l.quantity, unit_price=Money(amount=l.unit_price_amount, currency=row.currency),
                discount_amount=Money(amount=l.discount_amount, currency=row.currency), tax_amount=Money(amount=l.tax_amount, currency=row.currency),
                status=OrderLineItemStatus(l.status), price_snapshot_id=l.price_snapshot_id, reservation_id=l.reservation_id,
            )
            for l in row.lines.all()
        }
        payment_references = {
            p.id: OrderPaymentReference(id=p.id, payment_id=p.payment_id, amount=Money(amount=p.amount, currency=p.currency), status=PaymentReferenceStatus(p.status), processed_at=p.processed_at)
            for p in row.payment_references.all()
        }
        fulfillment_references = {
            f.id: OrderFulfillmentReference(id=f.id, fulfillment_id=f.fulfillment_id, status=FulfillmentReferenceStatus(f.status), tracking_number=TrackingNumber(f.tracking_number) if f.tracking_number else None, shipped_at=f.shipped_at, delivered_at=f.delivered_at)
            for f in row.fulfillment_references.all()
        }
        failures = [OrderFailure(id=x.id, reason=OrderFailureReason(x.reason), detail=x.detail, occurred_at=x.occurred_at) for x in row.failures.all()]
        status_history = [OrderStatusHistoryEntry(id=h.id, from_status=h.from_status, to_status=h.to_status, reason=h.reason, changed_at=h.changed_at, actor_id=h.actor_id) for h in row.status_history.all()]

        invoice = None
        if row.invoice_id is not None:
            invoice = OrderInvoice(id=row.invoice_id, invoice_number=row.invoice_number, total_amount=Money(amount=row.invoice_total_amount, currency=row.currency), status=InvoiceStatus(row.invoice_status), issued_at=row.invoice_issued_at)

        return Order(
            id=row.id, order_number=OrderNumber(row.order_number), customer_id=row.customer_id, cart_id=row.cart_id,
            shipping_address=_address_from_row(row, "shipping"), billing_address=_address_from_row(row, "billing"), currency=row.currency,
            order_type=OrderType(row.order_type), channel=OrderChannel(row.channel), status=OrderStatus(row.status), version=OrderVersion(row.version),
            lines=lines, coupon_ids=set(uuid.UUID(c) for c in row.coupon_ids), promotion_ids=set(uuid.UUID(p) for p in row.promotion_ids),
            payment_references=payment_references, fulfillment_references=fulfillment_references, invoice=invoice, failures=failures, status_history=status_history,
            note=OrderNote(row.note) if row.note else None, customer_comment=CustomerComment(row.customer_comment) if row.customer_comment else None,
            placed_at=row.placed_at, lock_reason=OrderLockReason(row.lock_reason) if row.lock_reason else None, is_archived=row.is_archived,
        )


class DjangoOrderReturnRepository:
    def get_by_id(self, return_id: uuid.UUID) -> OrderReturn | None:
        row = orm.OrderReturnModel.objects.filter(id=return_id).prefetch_related("lines").first()
        return self._to_domain(row) if row else None

    def get_by_return_number(self, return_number: str) -> OrderReturn | None:
        row = orm.OrderReturnModel.objects.filter(return_number=return_number).prefetch_related("lines").first()
        return self._to_domain(row) if row else None

    def list_for_order(self, order_id: uuid.UUID) -> list[OrderReturn]:
        rows = orm.OrderReturnModel.objects.filter(order_id=order_id).prefetch_related("lines")
        return [self._to_domain(r) for r in rows]

    def save(self, order_return: OrderReturn) -> OrderReturn:
        row, _ = orm.OrderReturnModel.objects.update_or_create(
            id=order_return.id,
            defaults={
                "return_number": order_return.return_number.value, "order_id": order_return.order_id, "status": order_return.status.value, "reason": order_return.reason.value,
                "refund_amount": order_return.refund_amount.amount if order_return.refund_amount else None, "refund_currency": order_return.refund_amount.currency if order_return.refund_amount else None,
                "requested_at": order_return.requested_at, "approved_at": order_return.approved_at, "received_at": order_return.received_at, "refunded_at": order_return.refunded_at,
            },
        )
        existing_line_ids = set(row.lines.values_list("id", flat=True))
        for line in order_return.lines.values():
            if line.id not in existing_line_ids:
                orm.ReturnLineItemModel.objects.create(id=line.id, order_return=row, order_line_item_id=line.order_line_item_id, quantity=line.quantity)
        return order_return

    def set_rejection_reason(self, return_id, reason: str) -> None:
        """The reason is customer-facing data the aggregate doesn't carry; stored beside it in the same transaction."""
        orm.OrderReturnModel.objects.filter(id=return_id).update(rejection_reason=(reason or "")[:2000])

    def _to_domain(self, row: orm.OrderReturnModel) -> OrderReturn:
        lines = {l.id: ReturnLineItem(id=l.id, order_line_item_id=l.order_line_item_id, quantity=l.quantity) for l in row.lines.all()}
        refund_amount = Money(amount=row.refund_amount, currency=row.refund_currency) if row.refund_amount is not None else None
        return OrderReturn(id=row.id, return_number=ReturnNumber(row.return_number), order_id=row.order_id, status=ReturnStatus(row.status), lines=lines, reason=ReturnReason(row.reason), refund_amount=refund_amount, requested_at=row.requested_at, approved_at=row.approved_at, received_at=row.received_at, refunded_at=row.refunded_at)


class DjangoOrderCancellationRepository:
    def get_by_id(self, cancellation_id: uuid.UUID) -> OrderCancellation | None:
        row = orm.OrderCancellationModel.objects.filter(id=cancellation_id).prefetch_related("lines").first()
        return self._to_domain(row) if row else None

    def list_for_order(self, order_id: uuid.UUID) -> list[OrderCancellation]:
        rows = orm.OrderCancellationModel.objects.filter(order_id=order_id).prefetch_related("lines")
        return [self._to_domain(r) for r in rows]

    def save(self, cancellation: OrderCancellation) -> OrderCancellation:
        row, _ = orm.OrderCancellationModel.objects.update_or_create(
            id=cancellation.id,
            defaults={
                "order_id": cancellation.order_id, "status": cancellation.status.value, "reason": cancellation.reason.value,
                "refund_amount": cancellation.refund_amount.amount if cancellation.refund_amount else None, "refund_currency": cancellation.refund_amount.currency if cancellation.refund_amount else None,
                "requested_at": cancellation.requested_at, "approved_at": cancellation.approved_at, "completed_at": cancellation.completed_at,
            },
        )
        existing_line_ids = set(row.lines.values_list("id", flat=True))
        for line in cancellation.lines.values():
            if line.id not in existing_line_ids:
                orm.CancellationLineItemModel.objects.create(id=line.id, cancellation=row, order_line_item_id=line.order_line_item_id, quantity=line.quantity)
        return cancellation

    def set_rejection_reason(self, cancellation_id, reason: str) -> None:
        orm.OrderCancellationModel.objects.filter(id=cancellation_id).update(rejection_reason=(reason or "")[:2000])

    def _to_domain(self, row: orm.OrderCancellationModel) -> OrderCancellation:
        lines = {l.id: CancellationLineItem(id=l.id, order_line_item_id=l.order_line_item_id, quantity=l.quantity) for l in row.lines.all()}
        refund_amount = Money(amount=row.refund_amount, currency=row.refund_currency) if row.refund_amount is not None else None
        return OrderCancellation(id=row.id, order_id=row.order_id, status=CancellationStatus(row.status), lines=lines, reason=CancellationReason(row.reason), refund_amount=refund_amount, requested_at=row.requested_at, approved_at=row.approved_at, completed_at=row.completed_at)
