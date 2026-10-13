from __future__ import annotations

import uuid
from decimal import Decimal

from apps.payment.application.gateway import GatewayChargeResult


class WebhookAuthenticator:
    """
    Provider-independent webhook-authentication interface (Phase 10b).
    No real provider is configured anywhere in this repository
    (confirmed by direct search), so no real signature scheme exists
    to implement. This interface isolates that concern so a real
    provider's actual documented verification can be plugged in later
    without touching ProcessPaymentCallback or the view.
    """

    def verify(self, headers: dict, raw_body: bytes) -> bool:
        raise NotImplementedError


class NotConfiguredWebhookAuthenticator(WebhookAuthenticator):
    """Honest default: always rejects. Matches this project's own NotImplementedPaymentGateway precedent -- fails loudly rather than pretending a security check exists."""

    def verify(self, headers: dict, raw_body: bytes) -> bool:
        return False


class FakeWebhookAuthenticator(WebhookAuthenticator):
    """
    Deterministic TEST-ONLY authenticator -- NOT a real signature
    scheme. Checks a shared test secret header
    ('X-Fake-Webhook-Secret') against a fixed test value. Explicitly
    NOT presented as production-grade; exists solely so
    ProcessPaymentCallback's real behavior can be exercised by
    automated tests without a real provider.
    """

    TEST_SECRET = "test-only-fake-webhook-secret-do-not-use-in-production"

    def verify(self, headers: dict, raw_body: bytes) -> bool:
        return headers.get("X-Fake-Webhook-Secret") == self.TEST_SECRET


class FakePaymentGateway:
    """
    Deterministic test double -- NOT a production gateway. No real
    provider is configured anywhere in this repository (confirmed by
    direct search: no CLICK_/PAYME_/UZUM_/PAYMENT_PROVIDER_* settings
    exist). This class exists so the payment architecture can be
    fully exercised by automated tests without fabricating credentials
    or pretending to call a real endpoint.

    Deterministic behavior, controlled by `order_reference`'s own
    content (a real caller passes the real order_id as a string; a
    test can suffix it to select behavior):
      - default: succeeds immediately
      - order_reference ending in "-FAIL": fails immediately
      - order_reference ending in "-PENDING": returns pending (caller must poll check_status)
    """

    def create_charge(self, amount: Decimal, currency: str, order_reference: str, idempotency_key: str) -> GatewayChargeResult:
        provider_reference = f"fake-{uuid.uuid4().hex[:16]}"
        if order_reference.endswith("-FAIL"):
            return GatewayChargeResult(provider_reference=provider_reference, status="failed")
        if order_reference.endswith("-PENDING"):
            return GatewayChargeResult(provider_reference=provider_reference, status="pending")
        return GatewayChargeResult(provider_reference=provider_reference, status="succeeded")

    def check_status(self, provider_reference: str) -> str:
        return "succeeded"


class NotImplementedPaymentGateway:
    """Matches this project's own existing naming convention (apps/ordering/infrastructure/gateways/payment_gateway.py) for the same 'no real provider yet' placeholder -- used as the default composition-root binding until a real provider is selected and configured."""

    def create_charge(self, amount: Decimal, currency: str, order_reference: str, idempotency_key: str):
        raise NotImplementedError("No real payment provider is configured. Use FakePaymentGateway for testing, or configure a real provider before production use.")

    def check_status(self, provider_reference: str):
        raise NotImplementedError("No real payment provider is configured.")
