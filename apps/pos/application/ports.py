"""
Application-layer ports (abstract interfaces) for POS.

**A disclosed, minimal exception, matching the identical precedent
already established in every prior module's own Application layer**:
Ports live in `application/ports.py`, never in `infrastructure/`.

**`SaleRepository` remains deliberately minimal, unchanged from POS
Phase 3's own certified state.**

**`ProductLookup` is new -- added for the POS Search module.**
Deliberately POS's own, narrow Port, not a re-export of Products'
own `application.ports.VariantRepository` Protocol -- Clean
Architecture's Dependency Inversion Principle puts the interface
definition with the *consumer*, not the *provider*. POS defines
exactly the two operations it needs (barcode/SKU exact lookup); it
does not need `get_product_id_for_variant`, so that method is
deliberately absent here even though Products' own Protocol has it.
The concrete implementation (in `infrastructure/composition.py`)
wraps Products' own composition-provided `DjangoVariantRepository`,
mirroring the identical Anti-Corruption-Layer pattern already
established by Products' own `PostgresSearchGateway` wrapping
`DjangoProductSearchBackend`.

**`PricingResolver` is new -- added for POS Phase 7 (Authoritative
Pricing Integration).** POS's own narrow abstraction over Pricing's
real, certified `CalculatePrice` Application Service -- a single
method, `calculate_price(price_list_id, variant_id, quantity, at,
coupon_code, region, membership_tier_code) -> Money`, deliberately
returning only the final `Money` value, never the full
`PriceCalculationResult` (which also exposes `base_price` and
`applied_discounts` -- internal Pricing structure this phase's own
Section 16 explicitly forbids exposing beyond what POS's own
contract requires). The concrete implementation wraps Pricing's own
composition-provided `CalculatePrice` service, mirroring the
identical composition-root-to-composition-root pattern already
established for `ProductLookup`/Products.

**A disclosed, load-bearing architectural finding**: `price_list_id`
must be supplied by the caller. No mapping from `Sale.branch_id` to
any Pricing concept (`price_list_id` or `region`) exists anywhere in
this repository -- `Branch` (Store's own aggregate) has no `region`
field, and `PriceList` has no `branch`/`store` reference. Inventing
such a mapping would be a speculative, out-of-scope addition (this
phase's own Section 18 forbids "unrelated refactors"); this boundary
is documented, not silently closed.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from apps.pos.domain.aggregates import Sale
from shared.value_objects.money import Money


class SaleRepository(Protocol):
    def get_by_id(self, sale_id: uuid.UUID) -> Sale | None: ...

    def save(self, sale: Sale) -> Sale: ...


class ProductLookup(Protocol):
    """POS-owned abstraction over Products' certified barcode/SKU identity -- never a duplicate Product model, only an exact-match identity lookup returning (product_id, variant_id)."""

    def find_by_barcode(self, barcode: str) -> tuple[uuid.UUID, uuid.UUID] | None: ...

    def find_by_sku(self, sku: str) -> tuple[uuid.UUID, uuid.UUID] | None: ...


class PricingResolver(Protocol):
    """POS-owned abstraction over Pricing's certified `CalculatePrice` Application Service -- never a duplicate pricing algorithm, only a resolution call returning the final, authoritative `Money`."""

    def calculate_price(self, price_list_id: uuid.UUID, variant_id: uuid.UUID, quantity: int = 1, at: datetime | None = None, coupon_code: str | None = None, region: str | None = None, membership_tier_code: str | None = None) -> Money: ...
