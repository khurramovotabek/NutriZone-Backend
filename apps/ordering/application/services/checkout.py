"""
Checkout Application Services: CreateOrderFromCart, CompleteCheckout.

`CreateOrderFromCart` is the real mechanism behind this phase's
Critical Validation finding -- see this phase's certification report
for the full explanation of why Cart's `/convert/` endpoint remains a
documented placeholder and how this service is the actual conversion
work, without importing Cart's domain.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.utils import timezone as django_timezone

from apps.ordering.application.ports import OrderRepository
from apps.ordering.application.services._shared import OrderingServiceContext
from apps.ordering.domain.aggregates import Order
from apps.ordering.domain.entities import OrderLineItem
from apps.ordering.domain.enums import OrderChannel
from apps.ordering.domain.exceptions import EmptyOrder
from apps.ordering.domain.services import OrderCreationPolicy
from apps.ordering.domain.value_objects import AddressSnapshot, CustomerComment, Money, OrderNumber
from common.exceptions import ValidationFailed


def _generate_order_number() -> str:
    return f"ORD-{uuid.uuid4().hex[:10].upper()}"


class CreateOrderFromCart:
    """
    Accepts already-extracted cart line-item/address data as plain
    parameters -- deliberately NEVER accepts or imports a live Cart
    aggregate. The Interfaces layer (a future phase) is responsible
    for loading the cart via Cart's own composition root, confirming
    it is checkout-ready, and extracting the primitives this service
    needs. This keeps Ordering's Application layer honestly isolated
    from Cart's domain, per this module's explicit 'never import
    Cart/Pricing/Inventory domain' rule -- the ID-only boundary is
    enforced at the call site, not just by convention.
    """

    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(
        self, cart_id: uuid.UUID | None, customer_id: uuid.UUID | None, currency: str,
        shipping_address: dict, billing_address: dict, line_items: list[dict], coupon_ids: list[uuid.UUID] | None = None,
        channel: str = OrderChannel.WEB.value, customer_comment: str | None = None,
    ) -> Order:
        with self._ctx.timer("order_create_from_cart_duration"):
            problems = OrderCreationPolicy.validate_preconditions(len(line_items), bool(shipping_address), bool(billing_address))
            if problems:
                raise ValidationFailed("Cannot create an order from this cart.", details={"fields": [{"field": "cart", "code": "PRECONDITION_FAILED", "message": p} for p in problems]})

            lines = [
                OrderLineItem(
                    id=uuid.uuid4(), product_variant_id=uuid.UUID(str(item["product_variant_id"])), quantity=item["quantity"],
                    unit_price=Money(amount=Decimal(str(item["unit_price"])), currency=currency),
                    discount_amount=Money(amount=Decimal(str(item.get("discount_amount", "0"))), currency=currency),
                    tax_amount=Money(amount=Decimal(str(item.get("tax_amount", "0"))), currency=currency),
                    price_snapshot_id=uuid.UUID(str(item["price_snapshot_id"])) if item.get("price_snapshot_id") else None,
                    reservation_id=uuid.UUID(str(item["reservation_id"])) if item.get("reservation_id") else None,
                )
                for item in line_items
            ]

            now = django_timezone.now()
            order, event = Order.create_from_cart_data(
                order_id=uuid.uuid4(), order_number=OrderNumber(_generate_order_number()), cart_id=cart_id, customer_id=customer_id,
                shipping_address=AddressSnapshot(**shipping_address), billing_address=AddressSnapshot(**billing_address),
                currency=currency, lines=lines, coupon_ids=set(coupon_ids or []), channel=OrderChannel(channel), at=now,
            )
            if customer_comment and customer_comment.strip():
                # The note the customer typed at checkout (delivery hints etc.) -- shown to staff as "From the customer".
                order.customer_comment = CustomerComment(customer_comment.strip()[:1000])
            saved = self._repo.save(order)

            self._ctx.stage_events([("OrderCreated", event.to_payload())])
            self._ctx.audit().created(entity_type="Order", entity_id=str(saved.id), after={"order_number": saved.order_number.value, "cart_id": str(cart_id) if cart_id else None})
            self._ctx.invalidate_ordering_cache()
            self._ctx.metric("orders_created_total")
            return saved


class CompleteCheckout:
    """
    Orchestrates the confirm-then-audit step once payment has been
    authorized -- a thin composition of `Order.confirm()` plus the
    cross-cutting steps, kept as its own named service (rather than
    folding into ConfirmOrder) because 'checkout completion' is a
    distinct customer-facing moment worth its own event/metric,
    even though today it triggers the identical domain transition.
    """

    def __init__(self, repo: OrderRepository, ctx: OrderingServiceContext) -> None:
        self._repo = repo
        self._ctx = ctx

    @transaction.atomic
    def execute(self, order_id: uuid.UUID) -> Order:
        from common.exceptions import ResourceNotFound

        order = self._repo.get_by_id(order_id)
        if order is None:
            raise ResourceNotFound("Order not found.")

        event = order.confirm(django_timezone.now())
        saved = self._repo.save(order)

        self._ctx.stage_events([("OrderConfirmed", event.to_payload())])
        self._ctx.audit().updated(entity_type="Order", entity_id=str(order_id), before={}, after={"status": "confirmed"})
        self._ctx.invalidate_ordering_cache()
        self._ctx.metric("checkouts_completed_total")
        return saved
