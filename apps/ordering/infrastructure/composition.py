"""
Composition root for the `ordering` module's interfaces layer.

Wires concrete `infrastructure/` implementations into `application/
services/` constructors -- matching every prior module's composition
root exactly. No service locator: every `build_*()` factory explicitly
constructs and returns one fully-wired object.
"""
from __future__ import annotations

import uuid

from apps.ordering.application.selectors import OrderSelector as ApplicationOrderSelector
from apps.ordering.application.services._shared import OrderingServiceContext
from apps.ordering.application.services.cancellations import (
    ApproveCancellation, CompleteCancellation, GetCancellation, ListCancellationsForOrder, RejectCancellation, RequestCancellation,
)
from apps.ordering.application.services.checkout import CompleteCheckout, CreateOrderFromCart
from apps.ordering.application.services.invoicing import IssueInvoice
from apps.ordering.application.services.lifecycle import (
    ArchiveOrder, CancelOrder, CompleteOrder, ConfirmOrder, DeliverOrder, ExpireOrder, LoadOrder, LockOrder,
    RestoreOrder, ShipOrder, StartOrderProcessing, UnlockOrder,
)
from apps.ordering.application.services.queries import AdminListOrders, GetOrderSummary, ListCustomerOrders, SearchOrders
from apps.ordering.application.services.references import (
    AttachCoupon, AttachPaymentReference, AttachPriceSnapshot, AttachReservation, AttachShipment, UpdateAddress,
    UpdatePaymentStatus,
)
from apps.ordering.application.services.returns import (
    ApproveReturn, GetReturn, ListReturnsForOrder, ReceiveReturn, RefundReturn, RejectReturn, RequestReturn,
)
from apps.ordering.infrastructure import models as orm
from apps.ordering.infrastructure.gateways.fulfillment_gateway import NotImplementedFulfillmentGateway
from apps.ordering.infrastructure.gateways.notification_gateway import NotImplementedNotificationGateway
from apps.ordering.infrastructure.gateways.payment_gateway import NotImplementedPaymentGateway
from apps.ordering.infrastructure.repositories import (
    DjangoOrderCancellationRepository, DjangoOrderRepository, DjangoOrderReturnRepository,
)
from apps.ordering.infrastructure.selectors import DjangoOrderSearchBackend
from core.outbox import stage_event


def stage_ordering_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(orm.OrderingOutboxEvent, event_type, payload)


def build_ordering_service_context(actor_id=None, actor_label: str = "") -> OrderingServiceContext:
    """Production context: outbox events + location stock for online orders (reserve on confirm, deduct on ship, ...)."""
    from apps.stores.infrastructure.online_fulfilment import StoresStockBridge

    return OrderingServiceContext(stage_events=stage_ordering_events, actor_id=actor_id, stock=StoresStockBridge(actor_label), actor_label=actor_label)


# --- Repositories / Selectors / Gateways --------------------------------

def build_order_repository() -> DjangoOrderRepository:
    return DjangoOrderRepository()


def build_order_return_repository() -> DjangoOrderReturnRepository:
    return DjangoOrderReturnRepository()


def build_order_cancellation_repository() -> DjangoOrderCancellationRepository:
    return DjangoOrderCancellationRepository()


def build_order_selector() -> ApplicationOrderSelector:
    return ApplicationOrderSelector(DjangoOrderSearchBackend())


def build_payment_gateway() -> NotImplementedPaymentGateway:
    return NotImplementedPaymentGateway()


def build_fulfillment_gateway() -> NotImplementedFulfillmentGateway:
    return NotImplementedFulfillmentGateway()


def build_notification_gateway() -> NotImplementedNotificationGateway:
    return NotImplementedNotificationGateway()


# --- Checkout ---------------------------------------------------------

def build_create_order_from_cart(actor_id=None) -> CreateOrderFromCart:
    return CreateOrderFromCart(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_complete_checkout(actor_id=None) -> CompleteCheckout:
    return CompleteCheckout(DjangoOrderRepository(), build_ordering_service_context(actor_id))


# --- Lifecycle -------------------------------------------------------

def build_load_order() -> LoadOrder:
    return LoadOrder(DjangoOrderRepository())


def build_confirm_order(actor_id=None) -> ConfirmOrder:
    return ConfirmOrder(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_start_order_processing(actor_id=None) -> StartOrderProcessing:
    return StartOrderProcessing(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_ship_order(actor_id=None) -> ShipOrder:
    return ShipOrder(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_deliver_order(actor_id=None) -> DeliverOrder:
    return DeliverOrder(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_complete_order(actor_id=None) -> CompleteOrder:
    return CompleteOrder(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_cancel_order(actor_id=None) -> CancelOrder:
    return CancelOrder(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_expire_order(actor_id=None) -> ExpireOrder:
    return ExpireOrder(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_lock_order(actor_id=None) -> LockOrder:
    return LockOrder(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_unlock_order(actor_id=None) -> UnlockOrder:
    return UnlockOrder(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_archive_order(actor_id=None) -> ArchiveOrder:
    return ArchiveOrder(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_restore_order(actor_id=None) -> RestoreOrder:
    return RestoreOrder(DjangoOrderRepository(), build_ordering_service_context(actor_id))


# --- References ------------------------------------------------------

def build_attach_shipment(actor_id=None) -> AttachShipment:
    return AttachShipment(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_attach_payment_reference(actor_id=None) -> AttachPaymentReference:
    return AttachPaymentReference(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_update_payment_status(actor_id=None) -> UpdatePaymentStatus:
    return UpdatePaymentStatus(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_attach_reservation(actor_id=None) -> AttachReservation:
    return AttachReservation(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_attach_price_snapshot(actor_id=None) -> AttachPriceSnapshot:
    return AttachPriceSnapshot(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_attach_coupon(actor_id=None) -> AttachCoupon:
    return AttachCoupon(DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_update_address(actor_id=None) -> UpdateAddress:
    return UpdateAddress(DjangoOrderRepository(), build_ordering_service_context(actor_id))


# --- Returns -----------------------------------------------------------

def build_request_return(actor_id=None) -> RequestReturn:
    return RequestReturn(DjangoOrderReturnRepository(), DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_approve_return(actor_id=None) -> ApproveReturn:
    return ApproveReturn(DjangoOrderReturnRepository(), build_ordering_service_context(actor_id))


def build_reject_return(actor_id=None) -> RejectReturn:
    return RejectReturn(DjangoOrderReturnRepository(), build_ordering_service_context(actor_id))


def build_receive_return(actor_id=None) -> ReceiveReturn:
    return ReceiveReturn(DjangoOrderReturnRepository(), build_ordering_service_context(actor_id), DjangoOrderRepository())


def build_refund_return(actor_id=None) -> RefundReturn:
    return RefundReturn(DjangoOrderReturnRepository(), build_ordering_service_context(actor_id))


def build_get_return() -> GetReturn:
    return GetReturn(DjangoOrderReturnRepository())


def build_list_returns_for_order() -> ListReturnsForOrder:
    return ListReturnsForOrder(DjangoOrderReturnRepository())


# --- Cancellations ---------------------------------------------------

def build_request_cancellation(actor_id=None) -> RequestCancellation:
    return RequestCancellation(DjangoOrderCancellationRepository(), DjangoOrderRepository(), build_ordering_service_context(actor_id))


def build_approve_cancellation(actor_id=None) -> ApproveCancellation:
    return ApproveCancellation(DjangoOrderCancellationRepository(), build_ordering_service_context(actor_id))


def build_reject_cancellation(actor_id=None) -> RejectCancellation:
    return RejectCancellation(DjangoOrderCancellationRepository(), build_ordering_service_context(actor_id))


def build_complete_cancellation(actor_id=None) -> CompleteCancellation:
    return CompleteCancellation(DjangoOrderCancellationRepository(), build_ordering_service_context(actor_id), DjangoOrderRepository())


def build_get_cancellation() -> GetCancellation:
    return GetCancellation(DjangoOrderCancellationRepository())


def build_list_cancellations_for_order() -> ListCancellationsForOrder:
    return ListCancellationsForOrder(DjangoOrderCancellationRepository())


# --- Invoicing ---------------------------------------------------------

def build_issue_invoice(actor_id=None) -> IssueInvoice:
    return IssueInvoice(DjangoOrderRepository(), build_ordering_service_context(actor_id))


# --- Queries --------------------------------------------------------------

def build_search_orders() -> SearchOrders:
    return SearchOrders(DjangoOrderSearchBackend())


def build_admin_list_orders() -> AdminListOrders:
    return AdminListOrders(DjangoOrderRepository())


def build_list_customer_orders() -> ListCustomerOrders:
    return ListCustomerOrders(DjangoOrderRepository())


def build_get_order_summary() -> GetOrderSummary:
    from apps.ordering.infrastructure.selectors import OrderSelector as InfraOrderSelector

    return GetOrderSummary(InfraOrderSelector())
