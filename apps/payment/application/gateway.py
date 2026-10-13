from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class GatewayChargeResult:
    """What a gateway returns immediately after being asked to charge -- a provider_reference to track the attempt, and whether it resolved synchronously or is still pending (e.g. awaiting a redirect + webhook)."""

    provider_reference: str
    status: str  # "pending" or "succeeded" or "failed" -- gateway-reported, never trusted as final until reconciled


class PaymentGateway(Protocol):
    """
    Provider-independent contract. Only the operations this project's
    actual current flow needs -- no refund/partial-capture methods,
    since no provider requiring them is selected yet (confirmed
    absent via direct search of env config and settings).
    """

    def create_charge(self, amount: Decimal, currency: str, order_reference: str, idempotency_key: str) -> GatewayChargeResult: ...

    def check_status(self, provider_reference: str) -> str: ...
