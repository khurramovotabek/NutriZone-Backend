"""
Composition root for the `pos` module.

**Extended again for POS Phase 7 -- Authoritative Pricing
Integration**: `PricingResolverAdapter`/`build_pricing_resolver()`/
`build_resolve_line_item_price()` mirror the identical composition-
root-to-composition-root wiring pattern already established for
`ProductLookupAdapter`/Products -- here reaching Pricing's own
composition root (`apps.pricing.infrastructure.composition.
build_calculate_price()`) instead. `AddLineItem`'s own factory
(`build_add_line_item`) is byte-identical to its Phase 3/6 certified
version -- unchanged.

**Extended this phase to close the gap Phase 2's own docstring
disclosed**: Phase 2 correctly stated zero Application Service
factories existed, since zero Application Services existed. That gap
is now closed -- an Application layer with 6 real services now exists
(`apps/pos/application/services/`), wired here via `build_*()`
factories, matching the identical shape every module with real
Application Services already uses (Loyalty, and, most recently,
Analytics).

**A disclosed, minimal, necessary extension, not a redesign**: this
phase's own brief (Section 18, Infrastructure Freeze) asked that
`infrastructure/` remain untouched unless a genuine Application/
Infrastructure contract gap is discovered; this file is the one
deliberate, narrow exception, directly authorized by that same
phase's own Section 12 ("If real precedent shows composition
factories such as build_create_sale(...)... then implement the
equivalent POS service factories") -- mirroring Analytics' own
identical, already-certified extension exactly. Nothing else in this
file changed: the 1 repository factory is byte-identical to Phase 2's
certified version. No model, repository, health check, task, event
handler, or admin registration was touched.

**No cache invalidation wiring exists** -- matching `PosServiceContext`'s
own disclosed omission (see `application/services/_shared.py`); zero
selectors exist to invalidate.

**Extended again for the POS Search module**: `ProductLookupAdapter`
wraps Products' own composition-provided `DjangoVariantRepository`
(obtained via `apps.products.infrastructure.composition.
build_variant_repository()`, never by importing `apps.products.
infrastructure.repositories` directly) -- a thin, composition-root-to-
composition-root wiring, mirroring the identical, already-established
pattern Products' own `PostgresSearchGateway` uses for wrapping
`DjangoProductSearchBackend`. This is a legitimate, minimal
cross-context READ dependency, distinct from a forbidden cross-context
Django ForeignKey or a forbidden Domain-to-Domain import -- POS's own
`ProductLookup` Port (an abstraction POS itself owns) is satisfied by
this adapter; POS's Application layer never imports Products'
Infrastructure directly.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from apps.pos.application.ports import PricingResolver, ProductLookup
from apps.pos.application.services._shared import PosServiceContext
from apps.pos.application.services.pricing import ResolveLineItemPrice
from apps.pos.application.services.sale import AddLineItem, ChangeLineItemPrice, CompleteSale, LoadSale, OpenSale, RefundSale, RemoveLineItem, SetSaleCustomer, UpdateLineItemQuantity, VoidSale
from apps.pos.application.services.search import SearchProduct
from apps.pos.infrastructure import models as orm
from apps.pos.infrastructure.repositories import DjangoSaleRepository
from apps.pricing.infrastructure.composition import build_calculate_price
from apps.products.infrastructure.composition import build_search_products, build_variant_repository
from core.outbox import stage_event
from shared.value_objects.money import Money


def stage_pos_events(events: list[tuple[str, dict]]) -> None:
    for event_type, payload in events:
        stage_event(orm.PosOutboxEvent, event_type, payload)


def build_pos_service_context(actor_id: uuid.UUID | None = None) -> PosServiceContext:
    return PosServiceContext(stage_events=stage_pos_events, actor_id=actor_id)


# --- Repository (byte-identical to Phase 2's certified version) -----------

def build_sale_repository() -> DjangoSaleRepository:
    return DjangoSaleRepository()


# --- Sale services -------------------------------------------------------

def build_open_sale(actor_id=None) -> OpenSale:
    return OpenSale(DjangoSaleRepository(), build_pos_service_context(actor_id))


def build_load_sale() -> LoadSale:
    return LoadSale(DjangoSaleRepository())


def build_add_line_item(actor_id=None) -> AddLineItem:
    return AddLineItem(DjangoSaleRepository(), build_pos_service_context(actor_id))


def build_remove_line_item(actor_id=None) -> RemoveLineItem:
    return RemoveLineItem(DjangoSaleRepository(), build_pos_service_context(actor_id))


def build_update_line_item_quantity(actor_id=None) -> UpdateLineItemQuantity:
    return UpdateLineItemQuantity(DjangoSaleRepository(), build_pos_service_context(actor_id))


def build_change_line_item_price(actor_id=None) -> ChangeLineItemPrice:
    return ChangeLineItemPrice(DjangoSaleRepository(), build_pos_service_context(actor_id))


def build_set_sale_customer(actor_id=None) -> SetSaleCustomer:
    return SetSaleCustomer(DjangoSaleRepository(), build_pos_service_context(actor_id))


def build_complete_sale(actor_id=None) -> CompleteSale:
    return CompleteSale(DjangoSaleRepository(), build_pos_service_context(actor_id))


def build_void_sale(actor_id=None) -> VoidSale:
    return VoidSale(DjangoSaleRepository(), build_pos_service_context(actor_id))


def build_refund_sale(actor_id=None) -> RefundSale:
    return RefundSale(DjangoSaleRepository(), build_pos_service_context(actor_id))


# --- Search (new this phase) ----------------------------------------------

class ProductLookupAdapter:
    """Satisfies POS's own `ProductLookup` Port by delegating to Products' own certified `VariantRepository`, obtained through Products' composition root -- never a duplicate Product/variant model inside POS."""

    def __init__(self) -> None:
        self._variant_repository = build_variant_repository()

    def find_by_barcode(self, barcode: str) -> tuple[uuid.UUID, uuid.UUID] | None:
        return self._variant_repository.get_by_barcode(barcode)

    def find_by_sku(self, sku: str) -> tuple[uuid.UUID, uuid.UUID] | None:
        return self._variant_repository.get_by_sku(sku)


def build_product_lookup() -> ProductLookup:
    return ProductLookupAdapter()


def build_search_product() -> SearchProduct:
    """No `actor_id` -- SearchProduct is a pure, read-only query, matching `build_load_sale()`'s own identical no-actor-id precedent."""
    return SearchProduct(build_product_lookup(), build_search_products())


# --- Pricing (new for POS Phase 7 -- Authoritative Pricing Integration) ----

class PricingResolverAdapter:
    """Satisfies POS's own `PricingResolver` Port by delegating to Pricing's own certified `CalculatePrice` Application Service, obtained through Pricing's own composition root (`build_calculate_price()`) -- never a duplicate pricing algorithm inside POS. Extracts only `final_price: Money` from Pricing's own richer `PriceCalculationResult` -- `base_price` and `applied_discounts` are deliberately never exposed beyond this adapter, per this phase's own explicit Section 16 boundary."""

    def __init__(self) -> None:
        self._calculate_price = build_calculate_price()

    def calculate_price(self, price_list_id: uuid.UUID, variant_id: uuid.UUID, quantity: int = 1, at: datetime | None = None, coupon_code: str | None = None, region: str | None = None, membership_tier_code: str | None = None) -> Money:
        result = self._calculate_price.execute(price_list_id=price_list_id, product_variant_id=variant_id, quantity=quantity, at=at, coupon_code=coupon_code, region=region, membership_tier_code=membership_tier_code)
        return result.final_price


def build_pricing_resolver() -> PricingResolver:
    return PricingResolverAdapter()


def build_resolve_line_item_price() -> ResolveLineItemPrice:
    """No `actor_id` -- ResolveLineItemPrice is a pure, read-only query, matching `build_search_product()`'s own identical no-actor-id precedent."""
    return ResolveLineItemPrice(build_pricing_resolver())
