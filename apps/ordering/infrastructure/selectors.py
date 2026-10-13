"""
Ordering read-model selectors -- optimized, read-only Postgres
queries. No business logic, no aggregate construction, matching the
pattern established by every prior module.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from django.db.models import Count, Sum
from django.utils import timezone as django_timezone

from apps.ordering.domain.enums import CancellationStatus, OrderLineItemStatus, OrderStatus, ReturnStatus
from apps.ordering.infrastructure import models as orm


class OrderSelector:
    def list(self, status: str | None, customer_id: uuid.UUID | None, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.OrderModel.objects.all()
        if status:
            qs = qs.filter(status=status)
        if customer_id:
            qs = qs.filter(customer_id=customer_id)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.annotate(line_count=Count("lines")).order_by("-created_at")[start : start + page_size]
        return [self._card(r) for r in rows], total

    def get_summary(self, order_id: uuid.UUID) -> dict | None:
        row = orm.OrderModel.objects.filter(id=order_id).annotate(line_count=Count("lines")).first()
        return self._card(row) if row else None

    def _card(self, row: orm.OrderModel) -> dict:
        line_count = row.line_count if hasattr(row, "line_count") else row.lines.count()
        return {
            "id": str(row.id), "order_number": row.order_number, "status": row.status, "currency": row.currency,
            "customer_id": str(row.customer_id) if row.customer_id else None, "line_count": line_count,
            "total_amount": str(row.invoice_total_amount) if row.invoice_total_amount is not None else None,
            "placed_at": row.placed_at.isoformat() if row.placed_at else None,
        }


class OrderReturnSelector:
    def list_for_order(self, order_id: uuid.UUID) -> list[dict]:
        rows = orm.OrderReturnModel.objects.filter(order_id=order_id)
        return [{"id": str(r.id), "return_number": r.return_number, "status": r.status} for r in rows]

    def list_pending(self) -> list[dict]:
        rows = orm.OrderReturnModel.objects.filter(status=ReturnStatus.REQUESTED.value)
        return [{"id": str(r.id), "return_number": r.return_number, "order_id": str(r.order_id)} for r in rows]


class OrderCancellationSelector:
    def list_for_order(self, order_id: uuid.UUID) -> list[dict]:
        rows = orm.OrderCancellationModel.objects.filter(order_id=order_id)
        return [{"id": str(c.id), "status": c.status} for c in rows]

    def list_pending(self) -> list[dict]:
        rows = orm.OrderCancellationModel.objects.filter(status=CancellationStatus.REQUESTED.value)
        return [{"id": str(c.id), "order_id": str(c.order_id)} for c in rows]


class ExpiringOrderSelector:
    """Backs the expire-orders Celery task."""

    def list_expiring(self, older_than_hours: int = 2) -> list[dict]:
        cutoff = django_timezone.now() - timedelta(hours=older_than_hours)
        rows = orm.OrderModel.objects.filter(status__in=[OrderStatus.DRAFT.value, OrderStatus.PENDING_PAYMENT.value], placed_at__isnull=False, placed_at__lte=cutoff)
        return [{"id": str(r.id), "order_number": r.order_number, "placed_at": r.placed_at.isoformat()} for r in rows]


class OrderStatisticsSelector:
    """Reporting helpers -- read-only aggregate queries for admin dashboards."""

    def counts_by_status(self) -> dict:
        rows = orm.OrderModel.objects.values("status").annotate(count=Count("id"))
        return {r["status"]: r["count"] for r in rows}

    def total_revenue_by_status(self, status: str, date_from=None, date_to=None) -> dict:
        """
        Authoritative revenue for a given Order status, computed
        directly from ACTIVE line items -- matching `Order.
        compute_total()`'s own exact formula (subtotal - discount +
        tax; shipping is deliberately excluded, since `compute_total()`
        itself excludes it) rather than `OrderInvoice.total_amount`,
        which is `None` unless an invoice was explicitly issued (a
        separate, optional operation) and would silently exclude any
        order without one.

        Returns a dict keyed by currency (e.g. `{"UZS": "1500000.00"}`)
        rather than one blended figure, since `OrderModel.currency`
        genuinely varies per order and summing across currencies would
        produce a meaningless number.

        `date_from`/`date_to` (Phase 08.2): optional, filters by
        `created_at`. Defaults to `None`/`None`, preserving every
        pre-existing caller's exact behavior -- confirmed by
        inspecting every call site before adding this parameter.
        """
        from django.db.models import DecimalField, ExpressionWrapper, F

        line_total_expr = ExpressionWrapper(
            F("lines__unit_price_amount") * F("lines__quantity") - F("lines__discount_amount") + F("lines__tax_amount"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
        qs = orm.OrderModel.objects.filter(status=status, lines__status=OrderLineItemStatus.ACTIVE.value)
        if date_from is not None:
            qs = qs.filter(created_at__gte=date_from)
        if date_to is not None:
            qs = qs.filter(created_at__lt=date_to)
        rows = qs.values("currency").annotate(total=Sum(line_total_expr))
        return {r["currency"]: str(r["total"] or 0) for r in rows}


class DjangoOrderSearchBackend:
    """Implements `application/ports.py::OrderSearchGateway` -- Postgres ILIKE search over order_number, per every other module's identical launch-stage search approach."""

    def search(self, query: str, filters: dict, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.OrderModel.objects.all()
        if query:
            qs = qs.filter(order_number__icontains=query)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.order_by("-created_at")[start : start + page_size]
        return [{"id": str(r.id), "order_number": r.order_number, "status": r.status} for r in rows], total
