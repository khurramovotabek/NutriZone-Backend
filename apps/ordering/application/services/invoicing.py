"""
Invoice Application Service.

Not explicitly named in this phase's brief's service list, but
`Order.issue_invoice()` is a real domain method with no other
Application Service reaching it -- 'Invoice numbering has its own
regulatory/sequential requirements' was already flagged in this
module's own design notes; the actual sequence authority lives at the
Infrastructure layer (a future database sequence), this service only
orchestrates calling it.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.ordering.application.ports import OrderRepository
from apps.ordering.application.services._shared import OrderingServiceContext
from apps.ordering.domain.aggregates import Order
from apps.ordering.domain.services import InvoiceNumberPolicy
from apps.ordering.domain.value_objects import Money
from common.exceptions import ResourceNotFound


class IssueInvoice:
    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID, sequence: int) -> Order:
        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")

        now = django_timezone.now()
        invoice_number = InvoiceNumberPolicy.format(sequence, now.year)
        total = order.compute_total()
        event = order.issue_invoice(invoice_number, total.grand_total, now)
        saved = self._repo.save(order)

        self._ctx.stage_events([("InvoiceIssued", event.to_payload())])
        self._ctx.audit().created(entity_type="OrderInvoice", entity_id=str(order.invoice.id), after={"order_id": str(order_id), "invoice_number": invoice_number})
        self._ctx.invalidate_ordering_cache()
        self._ctx.metric("invoices_issued_total")
        return saved
