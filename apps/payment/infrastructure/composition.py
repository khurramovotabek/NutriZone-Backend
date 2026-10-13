from __future__ import annotations

import uuid

from apps.ordering.infrastructure.composition import build_order_repository
from apps.payment.application.services._shared import PaymentServiceContext
from apps.payment.application.services.create_payment import CreatePayment
from apps.payment.application.services.webhook import ProcessPaymentCallback
from apps.payment.infrastructure.gateways import FakePaymentGateway, FakeWebhookAuthenticator, NotConfiguredWebhookAuthenticator, NotImplementedPaymentGateway
from apps.payment.infrastructure.models import PaymentOutboxEvent
from apps.payment.infrastructure.repositories import DjangoPaymentRepository
from core.outbox import stage_event


def stage_payment_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(PaymentOutboxEvent, event_type, payload)


def build_payment_service_context(actor_id: uuid.UUID | None = None) -> PaymentServiceContext:
    return PaymentServiceContext(stage_events=stage_payment_events, actor_id=actor_id)


def build_payment_repository() -> DjangoPaymentRepository:
    return DjangoPaymentRepository()


def build_payment_gateway():
    """
    Phase 10: no real payment provider is configured anywhere in this
    repository (confirmed by direct search of settings/env for
    CLICK_/PAYME_/UZUM_/PAYMENT_PROVIDER_* keys -- none exist). Per
    this phase's own explicit instruction not to fabricate a
    provider, the default binding is the honest
    NotImplementedPaymentGateway; only test composition explicitly
    substitutes FakePaymentGateway.
    """
    return NotImplementedPaymentGateway()


def build_create_payment(gateway=None) -> CreatePayment:
    return CreatePayment(
        order_repo=build_order_repository(),
        payment_repo=build_payment_repository(),
        gateway=gateway or build_payment_gateway(),
        ctx=build_payment_service_context(),
    )


def build_process_payment_callback() -> ProcessPaymentCallback:
    return ProcessPaymentCallback(
        payment_repo=build_payment_repository(),
        order_repo=build_order_repository(),
        ctx=build_payment_service_context(),
    )


def build_webhook_authenticator():
    """Phase 10b: no real provider signature scheme exists to implement (confirmed absent). Defaults to the honest NotConfiguredWebhookAuthenticator, which always rejects; only test composition explicitly substitutes FakeWebhookAuthenticator."""
    return NotConfiguredWebhookAuthenticator()
