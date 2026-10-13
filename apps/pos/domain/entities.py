"""
POS domain entities (non-root members of Sale).

**Only one entity exists**: `SaleLineItem`. Modeled as owned, not a
separate aggregate -- matching the established pattern from every
prior module's own owned-entity precedent (Notifications'
`NotificationDelivery`, Analytics' `SnapshotMetricEntry`): small,
bounded cardinality per sale, tightly consistency-coupled to its
parent, no independent query need.

**`product_id` is a plain `uuid.UUID`, never a `Product` import** --
POS must not import `apps.products.domain` (a forward dependency this
task's own Section 5 explicitly forbids); the line item references a
product only by identity, exactly matching the established
cross-context reference convention used throughout this build.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from apps.pos.domain.value_objects import Quantity
from shared.value_objects.money import Money


@dataclass(slots=True)
class SaleLineItem:
    id: uuid.UUID
    product_id: uuid.UUID
    quantity: Quantity
    unit_price: Money

    def line_total(self) -> Money:
        """Computed on demand from unit_price * quantity -- never stored as a separate, potentially-inconsistent field."""
        return self.unit_price * self.quantity.value
