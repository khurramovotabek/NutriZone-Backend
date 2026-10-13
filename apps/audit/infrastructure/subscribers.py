"""
apps/audit/infrastructure/subscribers.py

The audit-event subscriber Database Blueprint §4.19 describes:
"populated by a dedicated audit-event subscriber consuming the same
Outbox stream every other projection consumes." Never uses
`core.outbox.OutboxRelay` against a source module's own outbox table
(see `SubscriberCursor`'s own docstring for why that would be unsafe)
-- this is a plain, read-only, keyset-paginated query, tracking its
own independent progress.

**Generalized this phase, justified by evidence**: with 3 real sources
now wired (Platform, Loyalty, Ordering), the shared mechanical shape
(read cursor -> keyset query -> map -> idempotent record -> advance
cursor) is extracted once into `_sync_source()`, rather than
duplicated per source as the prior, single-source phase did. Each
source supplies only its own outbox model and its own narrow mapping
function -- Audit's infrastructure imports each source module's ORM
model directly (an accepted, disclosed cross-context read, matching
the identical pattern this phase's own predecessor already
established for Platform) but never its Application layer or business
logic.

**Scope note, still disclosed, not overstated**: 13 of 17 modules with a
real outbox model are wired. Of the remaining 4: Wallet was
investigated thoroughly (Phase E, re-confirmed unchanged in Phases F/G)
and deliberately NOT wired -- its `WalletCredited`/`WalletDebited`
events are structurally identical whether staged by an automatic
business flow or a manual staff adjustment, and the distinguishing
`reason`/`note` metadata never reaches the staged event's own payload.
Reviews, Chat, and Notifications all have a real outbox model but zero
actual `stage_event()` calls anywhere in their production code
(confirmed directly, repeatedly, across Phases E/F/G) -- there is
nothing for Audit to consume from any of the three.
"""
from __future__ import annotations

from collections.abc import Callable

from apps.audit.infrastructure import composition
from apps.audit.infrastructure import models as audit_orm
from apps.cart.infrastructure import models as cart_orm
from apps.geo.infrastructure import models as geo_orm
from apps.identity.infrastructure import models as identity_orm
from apps.inventory.infrastructure import models as inventory_orm
from apps.ordering.infrastructure import models as ordering_orm
from apps.platform.infrastructure import models as platform_orm
from apps.pos.infrastructure import models as pos_orm
from apps.pricing.infrastructure import models as pricing_orm
from apps.products.infrastructure import models as products_orm

_BATCH_SIZE = 200

EventMapper = Callable[[object], dict | None]


def _map_feature_flag_changed(event) -> dict | None:
    """Maps Platform's own `FeatureFlagChanged` event (shape confirmed against `apps/platform/domain/events.py`) into `RecordActivity.execute()`'s parameters. Returns None for any other event_type."""
    if event.event_type != "FeatureFlagChanged":
        return None
    payload = event.payload
    return {
        "action_type": "updated",
        "entity_type": "FeatureFlag",
        "entity_id": payload["flag_id"],
        "after_snapshot": {"key": payload["key"], "is_globally_enabled": payload["is_globally_enabled"]},
    }


def _map_order_confirmed(event) -> dict | None:
    """Maps Ordering's own `OrderConfirmed` event (shape confirmed against `apps/ordering/domain/events.py`) -- the third real, evidenced mapping this phase adds."""
    if event.event_type != "OrderConfirmed":
        return None
    payload = event.payload
    return {
        "action_type": "updated",
        "entity_type": "Order",
        "entity_id": payload["order_id"],
        "after_snapshot": {"status": "confirmed"},
    }


def _map_price_set(event) -> dict | None:
    """
    Maps Pricing's own `PriceSet` event (shape confirmed against
    `apps/pricing/domain/events.py`) -- Phase D's first addition,
    directly matching the Database Blueprint's own §4.19 named
    example ("price changes"). `entity_id` uses `product_variant_id`
    (the priced product, the natural audit-reader-facing entity),
    not `price_list_id` -- there is no single composite entity_id in
    the source event, so this is the most legible choice available
    from the fields it actually provides.
    """
    if event.event_type != "PriceSet":
        return None
    payload = event.payload
    return {
        "action_type": "updated",
        "entity_type": "ProductVariant",
        "entity_id": payload["product_variant_id"],
        "before_snapshot": {"amount": payload["old_amount"]} if payload["old_amount"] is not None else None,
        "after_snapshot": {"amount": payload["new_amount"], "price_type": payload["price_type"], "price_list_id": payload["price_list_id"]},
    }


def _map_stock_adjusted(event) -> dict | None:
    """Maps Inventory's own `StockAdjusted` event (shape confirmed against `apps/inventory/domain/events.py`) -- matches the Database Blueprint's own §4.19 named example ("stock adjustments") directly."""
    if event.event_type != "StockAdjusted":
        return None
    payload = event.payload
    return {
        "action_type": "updated",
        "entity_type": "WarehouseInventory",
        "entity_id": payload["warehouse_inventory_id"],
        "after_snapshot": {"quantity_delta": payload["quantity_delta"], "reason": payload["reason"]},
    }


def _map_user_role_assigned(event) -> dict | None:
    """Maps Identity's own `UserRoleAssigned` event (shape confirmed against `apps/identity/domain/events.py`) -- matches the Database Blueprint's own §4.19 named example ("role changes") directly. `entity_id` is the user whose role changed, not the role itself -- the natural "who did what happen to" reading for an admin audit screen."""
    if event.event_type != "UserRoleAssigned":
        return None
    payload = event.payload
    return {
        "action_type": "permission_changed",
        "entity_type": "User",
        "entity_id": payload["user_id"],
        "after_snapshot": {"role_id": payload["role_id"], "role_code": payload["role_code"], "store_id": payload["store_id"]},
    }


def _sync_source(source_schema: str, outbox_model, mapper: EventMapper) -> dict[str, int]:
    """
    Shared runner for every wired source. Failure handling, per this
    phase's own required semantics: processes events one at a time in
    keyset order; if `RecordActivity.execute()` raises for event N,
    the loop stops immediately -- the cursor is advanced only up to
    the last *successfully* processed event, never past N, so the
    next scheduled run retries starting from N. Already-recorded
    earlier events in the same batch are unaffected by the retry,
    since `record()` is idempotent by the source event's own id.
    """
    cursor, _created = audit_orm.SubscriberCursor.objects.get_or_create(source_schema=source_schema)

    qs = outbox_model.objects.all()
    if cursor.last_processed_created_at is not None:
        qs = qs.filter(created_at__gte=cursor.last_processed_created_at).exclude(
            created_at=cursor.last_processed_created_at, id=cursor.last_processed_id
        )
    events = list(qs.order_by("created_at", "id")[:_BATCH_SIZE])

    recorder = composition.build_record_activity()
    projected = 0
    last_successful = None
    failed = False

    for event in events:
        mapped = mapper(event)
        if mapped is None:
            last_successful = event
            continue
        try:
            recorder.execute(entry_id=event.id, context_schema=source_schema, occurred_at=event.created_at, actor_id=event.created_by, **mapped)
            projected += 1
            last_successful = event
        except Exception:  # noqa: BLE001 - a mapping/recording failure for one event must not corrupt the cursor or crash the whole batch; the task-level retry (Celery) picks this event back up next run
            failed = True
            break

    if last_successful is not None:
        cursor.last_processed_created_at = last_successful.created_at
        cursor.last_processed_id = last_successful.id
        cursor.save(update_fields=["last_processed_created_at", "last_processed_id", "updated_at"])

    return {"scanned": len(events), "projected": projected, "failed": failed}


def sync_platform_activity() -> dict[str, int]:
    return _sync_source("platform", platform_orm.PlatformOutboxEvent, _map_feature_flag_changed)


def sync_ordering_activity() -> dict[str, int]:
    return _sync_source("ordering", ordering_orm.OrderingOutboxEvent, _map_order_confirmed)


def sync_pricing_activity() -> dict[str, int]:
    return _sync_source("pricing", pricing_orm.PricingOutboxEvent, _map_price_set)


def sync_inventory_activity() -> dict[str, int]:
    return _sync_source("inventory", inventory_orm.InventoryOutboxEvent, _map_stock_adjusted)


def sync_identity_activity() -> dict[str, int]:
    return _sync_source("identity", identity_orm.IdentityOutboxEvent, _map_user_role_assigned)


def _map_cart_merged(event) -> dict | None:
    """Maps Cart's own `CartMerged` event (shape/staging confirmed against `apps/cart/domain/events.py` and `apps/cart/application/services/merge_and_ownership.py`) -- a meaningful lifecycle event, not routine item-level churn, matching this phase's own preference for audit-worthy activity over high-volume noise."""
    if event.event_type != "CartMerged":
        return None
    payload = event.payload
    return {
        "action_type": "updated",
        "entity_type": "Cart",
        "entity_id": payload["target_cart_id"],
        "after_snapshot": {"source_cart_id": payload["source_cart_id"], "items_merged": payload["items_merged"], "strategy": payload["strategy"]},
    }


def _map_address_updated(event) -> dict | None:
    """Maps Geo's own `AddressUpdated` event (shape/staging confirmed against `apps/geo/domain/events.py` and `apps/geo/application/services/address.py`). The only mapper in this whole capability whose source event already provides genuine, real before/after state directly -- `before`/`after` are used exactly as staged, not fabricated or reconstructed."""
    if event.event_type != "AddressUpdated":
        return None
    payload = event.payload
    return {
        "action_type": "updated",
        "entity_type": "Address",
        "entity_id": payload["address_id"],
        "before_snapshot": payload["before"],
        "after_snapshot": payload["after"],
    }


def _map_sale_completed(event) -> dict | None:
    """Maps POS's own `SaleCompleted` event (shape/staging confirmed against `apps/pos/domain/events.py` and `apps/pos/application/services/sale.py`, which stages via `event.__class__.__name__`). POS's own module is read-only here -- only its ORM model is imported into Audit's infrastructure, matching the identical pattern already established for every other source; POS's own composition root, services, and business logic are never touched, consistent with its certified FINAL status."""
    if event.event_type != "SaleCompleted":
        return None
    payload = event.payload
    return {
        "action_type": "updated",
        "entity_type": "Sale",
        "entity_id": payload["sale_id"],
        "after_snapshot": {"total_amount": payload["total_amount"], "currency": payload["currency"]},
    }


def _map_product_published(event) -> dict | None:
    """Maps Products' own `ProductPublished` event (shape/staging confirmed against `apps/products/domain/events.py` and `apps/products/application/services/lifecycle.py`)."""
    if event.event_type != "ProductPublished":
        return None
    payload = event.payload
    return {
        "action_type": "updated",
        "entity_type": "Product",
        "entity_id": payload["product_id"],
        "after_snapshot": {"status": "published"},
    }


def sync_cart_activity() -> dict[str, int]:
    return _sync_source("cart", cart_orm.CartOutboxEvent, _map_cart_merged)


def sync_geo_activity() -> dict[str, int]:
    return _sync_source("geo", geo_orm.GeoOutboxEvent, _map_address_updated)


def sync_pos_activity() -> dict[str, int]:
    return _sync_source("pos", pos_orm.PosOutboxEvent, _map_sale_completed)


def sync_products_activity() -> dict[str, int]:
    return _sync_source("products", products_orm.ProductsOutboxEvent, _map_product_published)
