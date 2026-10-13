"""
FulfillmentGateway -- Anti-Corruption Layer interface for a future
Fulfillment/Shipping module. Same rationale as PaymentGateway: read-
only status-check only, Ordering never triggers a shipment itself.
"""
from __future__ import annotations

import uuid
from typing import Protocol


class FulfillmentGateway(Protocol):
    def get_fulfillment_status(self, fulfillment_id: uuid.UUID) -> str | None: ...


class NotImplementedFulfillmentGateway:
    """Default composition-root binding until a real Fulfillment module exists."""

    def get_fulfillment_status(self, fulfillment_id: uuid.UUID) -> str | None:
        raise NotImplementedError("No Fulfillment module is registered yet. FulfillmentGateway is a placeholder interface, per this phase's explicit scope.")
