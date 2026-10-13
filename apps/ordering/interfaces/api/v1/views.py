"""
Ordering API views.

Thin per Django Implementation Blueprint §3: each view deserializes,
calls exactly one Application Service or Selector (resolved via
infrastructure/composition.py), and returns through the standard
response envelope. Every collection endpoint (list+create) is ONE
view class on ONE path. No view instantiates a repository, imports
infrastructure.models, constructs a domain aggregate, or calls a
private (underscore-prefixed) aggregate method.
"""
from __future__ import annotations

import uuid

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.ordering.infrastructure import composition
from apps.ordering.interfaces.api.v1.filters import parse_order_list_params
from apps.ordering.interfaces.api.v1.pagination import AdminOrderingPagination, OrderingPagination
from apps.ordering.interfaces.api.v1.permissions import (
    AdminOrder, ApproveCancellation, ApproveReturn, ArchiveOrder, CreateOrder, IssueInvoice, LockOrder,
    RefundReturn, RejectCancellation, RejectReturn, ReceiveReturn, RestoreOrder, UnlockOrder, UpdateOrder,
    ViewAnyOrder, ViewOwnOrder,
)
from apps.ordering.interfaces.api.v1.serializers import (
    AttachCouponSerializer, AttachPaymentSerializer, AttachPriceSnapshotSerializer, AttachReservationSerializer,
    AttachShipmentSerializer, CancelOrderSerializer, CompleteCancellationSerializer, CreateOrderSerializer,
    IssueInvoiceSerializer, LockOrderSerializer, RefundReturnSerializer, RejectCancellationSerializer,
    RejectReturnSerializer, RequestCancellationSerializer, RequestReturnSerializer, UpdateAddressSerializer,
    PaymentWebhookSerializer,
)
from apps.ordering.interfaces.api.v1.responses import paginated_response, success_response
from common.exceptions import ResourceNotFound
from common.exceptions import PermissionDenied as DomainPermissionDenied
from common.permissions import HasPermissionCode
from common.idempotency import protect_with_idempotency
from core.openapi import STANDARD_ERROR_RESPONSES
from core.ratelimit import ScopedRateLimitThrottle


def _responses(*codes: int) -> dict:
    return {code: STANDARD_ERROR_RESPONSES[code] for code in codes}


def _attach_identity(request) -> None:
    request.identity = request.user


def _require_order_ownership_or_staff(request, order_customer_id) -> None:
    """
    Phase 03A: closes a confirmed, proven CRITICAL IDOR affecting the
    entire Ordering module's read surface. `ViewOwnOrder` is a
    view-level-only permission check (DRF's `has_permission()`, run
    before any object is fetched) -- it cannot verify *which* order
    is being requested. Proven live before this fix: Customer A
    retrieved Customer B's full order (including `customer_id`) by
    order number alone, a 200 response with no ownership check
    anywhere in the call path, despite this permission's own
    docstring incorrectly claiming "object-level ownership is still
    checked separately by the view itself."

    Mirrors Wallet's own `_require_wallet_ownership_or_staff` fix
    exactly (same phase, same root cause, same resolution shape) --
    reuses the existing `HasPermissionCode` resolver, allowing a
    staff bypass via the pre-existing `ordering.order.view_any`
    permission code, no new authorization mechanism introduced.
    """
    if order_customer_id == getattr(request.user, "id", None):
        return
    resolver = HasPermissionCode.resolver
    if resolver is not None and resolver.user_has_permission(request.user.id, "ordering.order.view_any"):
        return
    raise DomainPermissionDenied("You do not have permission to view this order.")


def _actor_id(request):
    return getattr(getattr(request, "user", None), "id", None)


class OrderingThrottle(ScopedRateLimitThrottle):
    scope = "ordering.operation"
    limit = 3000
    window_seconds = 3600
    identifier_source = "user"


def _order_payload(order) -> dict:
    return {
        "id": str(order.id), "order_number": order.order_number.value, "customer_id": str(order.customer_id) if order.customer_id else None,
        "cart_id": str(order.cart_id) if order.cart_id else None, "currency": order.currency, "order_type": order.order_type.value,
        "channel": order.channel.value, "status": order.status.value, "version": order.version.value, "is_locked": order.lock_reason is not None,
        "lock_reason": order.lock_reason.value if order.lock_reason else None, "is_archived": order.is_archived,
        "lines": [_line_payload(l) for l in order.lines.values()], "coupon_ids": [str(c) for c in order.coupon_ids],
        "payment_references": [_payment_ref_payload(p) for p in order.payment_references.values()],
        "fulfillment_references": [_fulfillment_ref_payload(f) for f in order.fulfillment_references.values()],
        "invoice": _invoice_payload(order.invoice) if order.invoice else None,
        "shipping_address": _address_payload(order.shipping_address), "billing_address": _address_payload(order.billing_address),
        "note": order.note.text if order.note else None,
        "customer_comment": order.customer_comment.text if order.customer_comment else None, "placed_at": order.placed_at.isoformat() if order.placed_at else None,
        **_fulfilment_payload(order.id),
    }


def _fulfilment_payload(order_id) -> dict:
    """Delivery or pickup, and for pickup the branch the customer goes to (address, map point, hours, note)."""
    from apps.ordering.infrastructure.models import OrderModel
    from apps.stores.infrastructure.models import Store

    row = OrderModel.objects.filter(pk=order_id).values("fulfilment_method", "fulfilment_store_id").first() or {}
    method = row.get("fulfilment_method") or "delivery"
    store = Store.objects.filter(pk=row.get("fulfilment_store_id")).first() if method == "pickup" and row.get("fulfilment_store_id") else None
    pickup = None
    if store is not None:
        today = store.today_hours()
        pickup = {"name": store.name, "slug": store.slug, "address": ", ".join(x for x in (store.address, store.district, store.city) if x), "landmark": store.landmark,
                  "latitude": store.latitude, "longitude": store.longitude, "phone": (store.phone_numbers or [""])[0] if store.phone_numbers else "",
                  "note": store.pickup_note, "is_open_now": store.is_open_now(), "today": "" if today.get("closed") else f"{today.get('open', '')}–{today.get('close', '')}".strip("–")}
    return {"fulfilment_method": method, "pickup_store": pickup}


def _line_payload(line) -> dict:
    return {
        "id": str(line.id), "product_variant_id": str(line.product_variant_id), "quantity": line.quantity,
        "unit_price": {"amount": str(line.unit_price.amount), "currency": line.unit_price.currency},
        "discount_amount": {"amount": str(line.discount_amount.amount), "currency": line.discount_amount.currency},
        "tax_amount": {"amount": str(line.tax_amount.amount), "currency": line.tax_amount.currency},
        "line_total": {"amount": str(line.line_total().amount), "currency": line.line_total().currency},
        "status": line.status.value, "price_snapshot_id": str(line.price_snapshot_id) if line.price_snapshot_id else None,
        "reservation_id": str(line.reservation_id) if line.reservation_id else None,
    }


def _payment_ref_payload(ref) -> dict:
    return {"id": str(ref.id), "payment_id": str(ref.payment_id), "amount": {"amount": str(ref.amount.amount), "currency": ref.amount.currency}, "status": ref.status.value, "processed_at": ref.processed_at.isoformat() if ref.processed_at else None}


def _fulfillment_ref_payload(ref) -> dict:
    return {"id": str(ref.id), "fulfillment_id": str(ref.fulfillment_id), "status": ref.status.value, "tracking_number": str(ref.tracking_number) if ref.tracking_number else None, "shipped_at": ref.shipped_at.isoformat() if ref.shipped_at else None, "delivered_at": ref.delivered_at.isoformat() if ref.delivered_at else None}


def _invoice_payload(invoice) -> dict:
    return {"id": str(invoice.id), "invoice_number": invoice.invoice_number, "total_amount": {"amount": str(invoice.total_amount.amount), "currency": invoice.total_amount.currency}, "status": invoice.status.value, "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None}


def _address_payload(address) -> dict:
    return {"recipient_name": address.recipient_name, "line1": address.line1, "line2": address.line2, "city": address.city, "region": address.region, "postal_code": address.postal_code, "country_code": address.country_code, "phone": address.phone}


def _return_payload(order_return) -> dict:
    return {
        "id": str(order_return.id), "return_number": order_return.return_number.value, "order_id": str(order_return.order_id), "status": order_return.status.value, "reason": order_return.reason.value,
        "lines": [{"id": str(l.id), "order_line_item_id": str(l.order_line_item_id), "quantity": l.quantity} for l in order_return.lines.values()],
        "refund_amount": {"amount": str(order_return.refund_amount.amount), "currency": order_return.refund_amount.currency} if order_return.refund_amount else None,
        "requested_at": order_return.requested_at.isoformat() if order_return.requested_at else None,
    }


def _cancellation_payload(cancellation) -> dict:
    return {
        "id": str(cancellation.id), "order_id": str(cancellation.order_id), "status": cancellation.status.value, "reason": cancellation.reason.value,
        "lines": [{"id": str(l.id), "order_line_item_id": str(l.order_line_item_id), "quantity": l.quantity} for l in cancellation.lines.values()],
        "refund_amount": {"amount": str(cancellation.refund_amount.amount), "currency": cancellation.refund_amount.currency} if cancellation.refund_amount else None,
    }


def _load_order_by_number(order_number: str):
    return composition.build_load_order().execute(order_number=order_number)


# ============================================================
# Orders
# ============================================================


class OrderListCreateView(APIView):
    """Combined GET (list) + POST (create) at one path."""

    throttle_classes = [OrderingThrottle]

    def get_permissions(self):
        return [CreateOrder()] if self.request.method == "POST" else [ViewAnyOrder()]

    @extend_schema(tags=["Ordering Admin"], summary="List orders", responses={200: OpenApiResponse(description="Order collection"), **_responses(401, 403, 422)})
    def get(self, request):
        _attach_identity(request)
        params = parse_order_list_params(request.query_params)
        items, total = composition.build_admin_list_orders().execute(status=params.status, page=params.page, page_size=params.page_size)
        total_pages = max((total + params.page_size - 1) // params.page_size, 1)
        return paginated_response(data=[_order_payload(o) for o in items], pagination={"strategy": "page", "page": params.page, "page_size": params.page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Ordering"], summary="Create an order from cart data", request=CreateOrderSerializer, responses={201: OpenApiResponse(description="Order created"), **_responses(401, 403, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        def _create():
            return composition.build_create_order_from_cart(_actor_id(request)).execute(
                cart_id=data.get("cart_id"), customer_id=data.get("customer_id"), currency=data["currency"],
                shipping_address=data["shipping_address"], billing_address=data["billing_address"],
                line_items=[{**item, "unit_price": str(item["unit_price"]), "discount_amount": str(item["discount_amount"]), "tax_amount": str(item["tax_amount"])} for item in data["line_items"]],
                coupon_ids=data.get("coupon_ids"), channel=data["channel"],
            )

        return protect_with_idempotency(
            request, _actor_id(request), "ordering.create_order_from_cart", data,
            operation=_create, result_to_payload=_order_payload, success_status_code=201,
        )


class OrderDetailView(APIView):
    permission_classes = [ViewOwnOrder | ViewAnyOrder]

    @extend_schema(tags=["Ordering"], summary="Get an order by order number", responses={200: OpenApiResponse(description="Order detail"), **_responses(401, 403, 404)})
    def get(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        _require_order_ownership_or_staff(request, order.customer_id)
        return success_response(data=_order_payload(order))


class ConfirmOrderView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [UpdateOrder]

    @extend_schema(tags=["Ordering"], summary="Confirm an order", responses={200: OpenApiResponse(description="Confirmed"), **_responses(401, 403, 404, 409)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        saved = composition.build_confirm_order(_actor_id(request)).execute(order.id)
        return success_response(data=_order_payload(saved))


class CancelOrderView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [UpdateOrder]

    @extend_schema(tags=["Ordering"], summary="Cancel an order", request=CancelOrderSerializer, responses={200: OpenApiResponse(description="Cancelled"), **_responses(401, 403, 404, 409)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        serializer = CancelOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        saved = composition.build_cancel_order(_actor_id(request)).execute(order_id=order.id, **serializer.validated_data)
        return success_response(data=_order_payload(saved))


class ExpireOrderView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [AdminOrder]

    @extend_schema(tags=["Ordering Admin"], summary="Expire an order", responses={200: OpenApiResponse(description="Expired"), **_responses(401, 403, 404, 409)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        saved = composition.build_expire_order(_actor_id(request)).execute(order.id)
        return success_response(data=_order_payload(saved))


class StartOrderProcessingView(APIView):
    """Not in this phase's explicit endpoint list by URL, but `StartOrderProcessing`/`ShipOrder`/`DeliverOrder`/`CompleteOrder` are real Application Services (added during Phase 1 to close a gap between named domain methods and reachable services) with otherwise no way to reach them from the API at all -- added here so 'All Application Services reachable' (this phase's own explicit validation requirement) actually holds."""

    throttle_classes = [OrderingThrottle]
    permission_classes = [AdminOrder]

    @extend_schema(tags=["Ordering Admin"], summary="Start processing a confirmed order", responses={200: OpenApiResponse(description="Processing started"), **_responses(401, 403, 404, 409)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        saved = composition.build_start_order_processing(_actor_id(request)).execute(order.id)
        return success_response(data=_order_payload(saved))


class ShipOrderView(APIView):
    """Same rationale as StartOrderProcessingView."""

    throttle_classes = [OrderingThrottle]
    permission_classes = [AdminOrder]

    @extend_schema(tags=["Ordering Admin"], summary="Mark an order as shipped", responses={200: OpenApiResponse(description="Shipped"), **_responses(401, 403, 404, 409)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        saved = composition.build_ship_order(_actor_id(request)).execute(order.id)
        return success_response(data=_order_payload(saved))


class DeliverOrderView(APIView):
    """Same rationale as StartOrderProcessingView."""

    throttle_classes = [OrderingThrottle]
    permission_classes = [AdminOrder]

    @extend_schema(tags=["Ordering Admin"], summary="Mark an order as delivered", responses={200: OpenApiResponse(description="Delivered"), **_responses(401, 403, 404, 409)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        saved = composition.build_deliver_order(_actor_id(request)).execute(order.id)
        return success_response(data=_order_payload(saved))


class CompleteOrderView(APIView):
    """Same rationale as StartOrderProcessingView."""

    throttle_classes = [OrderingThrottle]
    permission_classes = [AdminOrder]

    @extend_schema(tags=["Ordering Admin"], summary="Mark an order as completed", responses={200: OpenApiResponse(description="Completed"), **_responses(401, 403, 404, 409)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        saved = composition.build_complete_order(_actor_id(request)).execute(order.id)
        return success_response(data=_order_payload(saved))


class LockOrderView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [LockOrder]

    @extend_schema(tags=["Ordering Admin"], summary="Lock an order", request=LockOrderSerializer, responses={200: OpenApiResponse(description="Locked"), **_responses(401, 403, 404, 409)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        serializer = LockOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        saved = composition.build_lock_order(_actor_id(request)).execute(order_id=order.id, **serializer.validated_data)
        return success_response(data=_order_payload(saved))


class UnlockOrderView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [UnlockOrder]

    @extend_schema(tags=["Ordering Admin"], summary="Unlock an order", responses={200: OpenApiResponse(description="Unlocked"), **_responses(401, 403, 404, 409)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        saved = composition.build_unlock_order(_actor_id(request)).execute(order.id)
        return success_response(data=_order_payload(saved))


class ArchiveOrderView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [ArchiveOrder]

    @extend_schema(tags=["Ordering Admin"], summary="Archive an order", responses={200: OpenApiResponse(description="Archived"), **_responses(401, 403, 404, 409)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        saved = composition.build_archive_order(_actor_id(request)).execute(order.id)
        return success_response(data=_order_payload(saved))


class RestoreOrderView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [RestoreOrder]

    @extend_schema(tags=["Ordering Admin"], summary="Restore an archived order", responses={200: OpenApiResponse(description="Restored"), **_responses(401, 403, 404, 409)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        saved = composition.build_restore_order(_actor_id(request)).execute(order.id)
        return success_response(data=_order_payload(saved))


class OrderShipmentView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [UpdateOrder]

    @extend_schema(tags=["Ordering"], summary="Attach a fulfillment reference to the order", request=AttachShipmentSerializer, responses={200: OpenApiResponse(description="Attached"), **_responses(401, 403, 404, 422)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        serializer = AttachShipmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        saved = composition.build_attach_shipment(_actor_id(request)).execute(order_id=order.id, **serializer.validated_data)
        return success_response(data=_order_payload(saved))


class OrderPaymentView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [UpdateOrder]

    @extend_schema(tags=["Ordering"], summary="Attach a payment reference to the order", request=AttachPaymentSerializer, responses={200: OpenApiResponse(description="Attached"), **_responses(401, 403, 404, 422)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        serializer = AttachPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        saved = composition.build_attach_payment_reference(_actor_id(request)).execute(order_id=order.id, **serializer.validated_data)
        return success_response(data=_order_payload(saved))


class PaymentWebhookView(APIView):
    """
    Phase 02E's internal, provider-agnostic payment webhook (Step 7).
    `AllowAny` deliberately, matching Step 13's own explicit
    instruction that provider callbacks "must use signature/
    authentication mechanisms rather than normal user authentication"
    -- the HMAC signature check below is this endpoint's real security
    boundary, not JWT/permission-code authorization.
    """

    throttle_classes = [OrderingThrottle]
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["Ordering"], summary="Payment provider webhook callback", request=PaymentWebhookSerializer, responses={200: OpenApiResponse(description="Processed"), **_responses(401, 404, 409, 422)})
    def post(self, request):
        import hashlib
        import hmac

        from django.conf import settings
        from django.db import IntegrityError, transaction as db_transaction

        from apps.ordering.domain.enums import PaymentReferenceStatus
        from apps.ordering.infrastructure import models as orm
        from common.exceptions import AuthenticationRequired, ConflictError, ValidationFailed

        raw_body = request.body
        signature = request.headers.get("X-Payment-Signature", "")
        expected = hmac.new(settings.PAYMENT_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
        if not signature or not hmac.compare_digest(signature, expected):
            # Never processed, never recorded -- an unsigned/forged
            # request carries no trustworthy provider_transaction_id
            # to key a PaymentWebhookDelivery row on in the first
            # place, and recording one here would let a malicious
            # sender squat on a real provider's future transaction id.
            raise AuthenticationRequired("Invalid or missing webhook signature.")

        serializer = PaymentWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        event_type_to_status = {
            "authorized": PaymentReferenceStatus.AUTHORIZED, "captured": PaymentReferenceStatus.CAPTURED,
            "failed": PaymentReferenceStatus.FAILED, "refunded": PaymentReferenceStatus.REFUNDED,
            "partially_refunded": PaymentReferenceStatus.PARTIALLY_REFUNDED,
        }
        status = event_type_to_status[data["event_type"]]

        pending_error = None
        with db_transaction.atomic():
            try:
                delivery = orm.PaymentWebhookDelivery.objects.create(
                    provider=data["provider"], provider_transaction_id=data["provider_transaction_id"],
                    order_id=data["order_id"], event_type=data["event_type"], amount=data["amount"], currency=data["currency"],
                    status=orm.PaymentWebhookDeliveryStatus.PROCESSED,
                )
            except IntegrityError:
                # Step 8: a genuine duplicate delivery of the same
                # provider transaction -- already processed (or
                # rejected) exactly once; returning success here
                # (rather than reprocessing) is what makes a retried
                # webhook harmless.
                return success_response(data={"status": "already_processed"})

            order = composition.build_order_repository().get_by_id(data["order_id"])
            if order is None:
                delivery.status = orm.PaymentWebhookDeliveryStatus.REJECTED
                delivery.rejection_reason = "order_not_found"
                delivery.save(update_fields=["status", "rejection_reason"])
                pending_error = ResourceNotFound("Order not found.")
            else:
                payment_ref = next((r for r in order.payment_references.values() if r.payment_id == data["payment_id"]), None)
                if payment_ref is None:
                    delivery.status = orm.PaymentWebhookDeliveryStatus.REJECTED
                    delivery.rejection_reason = "unknown_payment_reference"
                    delivery.save(update_fields=["status", "rejection_reason"])
                    pending_error = ValidationFailed("No matching payment reference found on this order.")
                elif payment_ref.amount.currency != data["currency"] or payment_ref.amount.amount != data["amount"]:
                    # Step 4/5: never trust the webhook's own amount/currency --
                    # they must match what was already recorded server-side
                    # when the payment reference was attached.
                    delivery.status = orm.PaymentWebhookDeliveryStatus.REJECTED
                    delivery.rejection_reason = "amount_or_currency_mismatch"
                    delivery.save(update_fields=["status", "rejection_reason"])
                    pending_error = ConflictError("Webhook amount/currency does not match the recorded payment reference.")
                else:
                    delivery.payment_reference_id = payment_ref.id
                    delivery.save(update_fields=["payment_reference_id"])
                    # Phase 15H: moved inside this same atomic() block --
                    # previously called after the block closed, meaning a
                    # failure here left the already-committed delivery
                    # record permanently inconsistent with the real,
                    # never-updated Order state (the exact class of bug
                    # already found and fixed once before, in Phase 09.7c's
                    # own CheckoutCartView).
                    saved = composition.build_update_payment_status(None).execute(order_id=order.id, payment_reference_id=payment_ref.id, status=status)

        if pending_error is not None:
            # Raised only after the atomic block above has already
            # committed -- a rejected delivery must genuinely persist
            # (Step 16's observability requirement), not be rolled
            # back by the very exception that reports the rejection.
            raise pending_error

        return success_response(data=_order_payload(saved))


class OrderCouponView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [UpdateOrder]

    @extend_schema(tags=["Ordering"], summary="Attach a coupon reference to the order", request=AttachCouponSerializer, responses={200: OpenApiResponse(description="Attached"), **_responses(401, 403, 404, 422)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        serializer = AttachCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        saved = composition.build_attach_coupon(_actor_id(request)).execute(order_id=order.id, **serializer.validated_data)
        return success_response(data=_order_payload(saved))


class OrderAddressView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [UpdateOrder]

    @extend_schema(tags=["Ordering"], summary="Update the order's shipping/billing address", request=UpdateAddressSerializer, responses={200: OpenApiResponse(description="Updated"), **_responses(401, 403, 404, 422)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        serializer = UpdateAddressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        saved = composition.build_update_address(_actor_id(request)).execute(order_id=order.id, **serializer.validated_data)
        return success_response(data=_order_payload(saved))


class OrderReservationView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [UpdateOrder]

    @extend_schema(tags=["Ordering"], summary="Re-attach an inventory reservation reference to a line item", request=AttachReservationSerializer, responses={200: OpenApiResponse(description="Attached"), **_responses(401, 403, 404, 422)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        serializer = AttachReservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        saved = composition.build_attach_reservation(_actor_id(request)).execute(order_id=order.id, **serializer.validated_data)
        return success_response(data=_order_payload(saved))


class OrderPriceSnapshotView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [UpdateOrder]

    @extend_schema(tags=["Ordering"], summary="Re-attach a price snapshot reference to a line item", request=AttachPriceSnapshotSerializer, responses={200: OpenApiResponse(description="Attached"), **_responses(401, 403, 404, 422)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        serializer = AttachPriceSnapshotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        saved = composition.build_attach_price_snapshot(_actor_id(request)).execute(order_id=order.id, **serializer.validated_data)
        return success_response(data=_order_payload(saved))


class IssueInvoiceView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [IssueInvoice]

    @extend_schema(tags=["Invoice Operations"], summary="Issue an invoice for the order", request=IssueInvoiceSerializer, responses={200: OpenApiResponse(description="Invoice issued"), **_responses(401, 403, 404, 409)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        serializer = IssueInvoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        saved = composition.build_issue_invoice(_actor_id(request)).execute(order_id=order.id, **serializer.validated_data)
        return success_response(data=_order_payload(saved))


class InvoiceDetailView(APIView):
    permission_classes = [ViewOwnOrder | ViewAnyOrder]

    @extend_schema(tags=["Invoice Operations"], summary="Get the order's invoice", responses={200: OpenApiResponse(description="Invoice"), **_responses(401, 403, 404)})
    def get(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        _require_order_ownership_or_staff(request, order.customer_id)
        if order.invoice is None:
            raise ResourceNotFound("This order has no invoice yet.")
        return success_response(data=_invoice_payload(order.invoice))


# ============================================================
# Returns
# ============================================================


class ReturnListCreateView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [ViewOwnOrder | ViewAnyOrder]

    def get_permissions(self):
        return [UpdateOrder()] if self.request.method == "POST" else [(ViewOwnOrder | ViewAnyOrder)()]

    @extend_schema(tags=["Return Operations"], summary="List returns for an order")
    def get(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        _require_order_ownership_or_staff(request, order.customer_id)
        returns = composition.build_list_returns_for_order().execute(order.id)
        return success_response(data=[_return_payload(r) for r in returns])

    @extend_schema(tags=["Return Operations"], summary="Request a return for an order", request=RequestReturnSerializer, responses={201: OpenApiResponse(description="Return requested"), **_responses(401, 403, 404, 422)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        serializer = RequestReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_return = composition.build_request_return(_actor_id(request)).execute(order_id=order.id, **serializer.validated_data)
        return success_response(data=_return_payload(order_return), status_code=201)


class ApproveReturnView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [ApproveReturn]

    @extend_schema(tags=["Return Operations"], summary="Approve a return", responses={200: OpenApiResponse(description="Approved"), **_responses(401, 403, 404, 409)})
    def post(self, request, return_id: str):
        _attach_identity(request)
        order_return = composition.build_approve_return(_actor_id(request)).execute(uuid.UUID(return_id))
        return success_response(data=_return_payload(order_return))


class RejectReturnView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [RejectReturn]

    @extend_schema(tags=["Return Operations"], summary="Reject a return", request=RejectReturnSerializer, responses={200: OpenApiResponse(description="Rejected"), **_responses(401, 403, 404, 409)})
    def post(self, request, return_id: str):
        _attach_identity(request)
        serializer = RejectReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_return = composition.build_reject_return(_actor_id(request)).execute(return_id=uuid.UUID(return_id), **serializer.validated_data)
        return success_response(data=_return_payload(order_return))


class ReceiveReturnView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [ReceiveReturn]

    @extend_schema(tags=["Return Operations"], summary="Mark a return as received", responses={200: OpenApiResponse(description="Received"), **_responses(401, 403, 404, 409)})
    def post(self, request, return_id: str):
        _attach_identity(request)
        order_return = composition.build_receive_return(_actor_id(request)).execute(uuid.UUID(return_id))
        return success_response(data=_return_payload(order_return))


class RefundReturnView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [RefundReturn]

    @extend_schema(tags=["Return Operations"], summary="Refund a return", request=RefundReturnSerializer, responses={200: OpenApiResponse(description="Refunded"), **_responses(401, 403, 404, 409)})
    def post(self, request, return_id: str):
        _attach_identity(request)
        serializer = RefundReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order_return = composition.build_refund_return(_actor_id(request)).execute(return_id=uuid.UUID(return_id), **serializer.validated_data)
        return success_response(data=_return_payload(order_return))


class ReturnDetailView(APIView):
    """Not in this phase's explicit endpoint list by URL, but `GetReturn` is a real query service with no other reachable endpoint -- added for the same 'all Application Services reachable' reason as the order status-transition views above."""

    permission_classes = [ViewOwnOrder | ViewAnyOrder]

    @extend_schema(tags=["Return Operations"], summary="Get a single return by id", responses={200: OpenApiResponse(description="Return detail"), **_responses(401, 403, 404)})
    def get(self, request, return_id: str):
        _attach_identity(request)
        order_return = composition.build_get_return().execute(uuid.UUID(return_id))
        parent_order = composition.build_order_repository().get_by_id(order_return.order_id)
        if parent_order is not None:
            _require_order_ownership_or_staff(request, parent_order.customer_id)
        return success_response(data=_return_payload(order_return))


# ============================================================
# Cancellations
# ============================================================


class CancellationListCreateView(APIView):
    throttle_classes = [OrderingThrottle]

    def get_permissions(self):
        return [UpdateOrder()] if self.request.method == "POST" else [(ViewOwnOrder | ViewAnyOrder)()]

    @extend_schema(tags=["Cancellation Operations"], summary="List cancellations for an order")
    def get(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        _require_order_ownership_or_staff(request, order.customer_id)
        cancellations = composition.build_list_cancellations_for_order().execute(order.id)
        return success_response(data=[_cancellation_payload(c) for c in cancellations])

    @extend_schema(tags=["Cancellation Operations"], summary="Request a formal cancellation for an order", request=RequestCancellationSerializer, responses={201: OpenApiResponse(description="Cancellation requested"), **_responses(401, 403, 404, 422)})
    def post(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        serializer = RequestCancellationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancellation = composition.build_request_cancellation(_actor_id(request)).execute(order_id=order.id, **serializer.validated_data)
        return success_response(data=_cancellation_payload(cancellation), status_code=201)


class ApproveCancellationView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [ApproveCancellation]

    @extend_schema(tags=["Cancellation Operations"], summary="Approve a formal cancellation request", responses={200: OpenApiResponse(description="Approved"), **_responses(401, 403, 404, 409)})
    def post(self, request, cancellation_id: str):
        _attach_identity(request)
        cancellation = composition.build_approve_cancellation(_actor_id(request)).execute(uuid.UUID(cancellation_id))
        return success_response(data=_cancellation_payload(cancellation))


class RejectCancellationView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [RejectCancellation]

    @extend_schema(tags=["Cancellation Operations"], summary="Reject a formal cancellation request", request=RejectCancellationSerializer, responses={200: OpenApiResponse(description="Rejected"), **_responses(401, 403, 404, 409)})
    def post(self, request, cancellation_id: str):
        _attach_identity(request)
        serializer = RejectCancellationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancellation = composition.build_reject_cancellation(_actor_id(request)).execute(cancellation_id=uuid.UUID(cancellation_id), **serializer.validated_data)
        return success_response(data=_cancellation_payload(cancellation))


class CompleteCancellationView(APIView):
    throttle_classes = [OrderingThrottle]
    permission_classes = [ApproveCancellation]

    @extend_schema(tags=["Cancellation Operations"], summary="Complete an approved cancellation", request=CompleteCancellationSerializer, responses={200: OpenApiResponse(description="Completed"), **_responses(401, 403, 404, 409)})
    def post(self, request, cancellation_id: str):
        _attach_identity(request)
        serializer = CompleteCancellationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancellation = composition.build_complete_cancellation(_actor_id(request)).execute(cancellation_id=uuid.UUID(cancellation_id), **serializer.validated_data)
        return success_response(data=_cancellation_payload(cancellation))


class CancellationDetailView(APIView):
    """Same rationale as ReturnDetailView -- exposes `GetCancellation`."""

    permission_classes = [ViewOwnOrder | ViewAnyOrder]

    @extend_schema(tags=["Cancellation Operations"], summary="Get a single cancellation by id", responses={200: OpenApiResponse(description="Cancellation detail"), **_responses(401, 403, 404)})
    def get(self, request, cancellation_id: str):
        _attach_identity(request)
        cancellation = composition.build_get_cancellation().execute(uuid.UUID(cancellation_id))
        parent_order = composition.build_order_repository().get_by_id(cancellation.order_id)
        if parent_order is not None:
            _require_order_ownership_or_staff(request, parent_order.customer_id)
        return success_response(data=_cancellation_payload(cancellation))


# ============================================================
# Queries: Customer Orders / Admin / Search / Summary / Statistics
# ============================================================


class CustomerOrdersView(APIView):
    permission_classes = [ViewOwnOrder | ViewAnyOrder]

    @extend_schema(tags=["Ordering"], summary="List a customer's orders")
    def get(self, request, customer_id: str):
        _attach_identity(request)
        _require_order_ownership_or_staff(request, uuid.UUID(customer_id))
        pagination = OrderingPagination.from_query_params(request.query_params)
        status_filter = request.query_params.get("filter[status]")
        items, total = composition.build_list_customer_orders().execute(uuid.UUID(customer_id), status=status_filter, page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=[_order_payload(o) for o in items], pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})


class OrderSearchView(APIView):
    permission_classes = [AdminOrder]

    @extend_schema(tags=["Ordering Admin"], summary="Search orders")
    def get(self, request):
        _attach_identity(request)
        pagination = AdminOrderingPagination.from_query_params(request.query_params)
        query = request.query_params.get("q", "")
        results, total = composition.build_search_orders().execute(query=query, filters={}, page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=results, pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})


class OrderSummaryView(APIView):
    permission_classes = [ViewOwnOrder | ViewAnyOrder]

    @extend_schema(tags=["Ordering"], summary="Get a lightweight order summary (CQRS read side)")
    def get(self, request, number: str):
        _attach_identity(request)
        order = _load_order_by_number(number)
        _require_order_ownership_or_staff(request, order.customer_id)
        summary = composition.build_get_order_summary().execute(order.id)
        return success_response(data=summary)


class AdminOrderListView(APIView):
    """Wires the existing, already N+1-safe `OrderSelector.list()` (newest-first, `line_count` pre-annotated per Phase 02I's own fix) -- built but never exposed via HTTP."""

    permission_classes = [AdminOrder]

    @extend_schema(tags=["Ordering Admin"], summary="List orders (newest first) -- recent orders / order-status filtering for dashboard use")
    def get(self, request):
        _attach_identity(request)
        from apps.ordering.infrastructure.selectors import OrderSelector

        pagination = AdminOrderingPagination.from_query_params(request.query_params)
        status_filter = request.query_params.get("filter[status]")
        customer_id_filter = request.query_params.get("filter[customer_id]")
        items, total = OrderSelector().list(
            status=status_filter,
            customer_id=uuid.UUID(customer_id_filter) if customer_id_filter else None,
            page=pagination.page, page_size=pagination.page_size,
        )
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=items, pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})


class OrderStatisticsView(APIView):
    permission_classes = [AdminOrder]

    @extend_schema(tags=["Ordering Admin"], summary="Order statistics (counts by status, revenue by status)")
    def get(self, request):
        _attach_identity(request)
        from apps.ordering.domain.enums import OrderStatus
        from apps.ordering.infrastructure.selectors import OrderStatisticsSelector
        from common.exceptions import ValidationFailed

        status_param = request.query_params.get("status", OrderStatus.COMPLETED.value)
        valid_statuses = {s.value for s in OrderStatus}
        if status_param not in valid_statuses:
            raise ValidationFailed(f"Invalid status '{status_param}'.", details={"fields": [{"field": "status", "code": "INVALID_CHOICE"}]})

        selector = OrderStatisticsSelector()
        return success_response(data={
            "counts_by_status": selector.counts_by_status(),
            "revenue_by_status": {"status": status_param, "revenue_by_currency": selector.total_revenue_by_status(status_param)},
        })
