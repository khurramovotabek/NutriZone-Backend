"""
Online orders against location stock (the WMS truth, see stock_service.py).

Lifecycle, every step a stock_service.move() ledger row with reference = the order number:

  * confirm  -> RESERVATION at the fulfilment warehouse, as much as is free (best effort: a shortage
               never blocks confirming; the order page shows it so the dispatcher can act).
  * ship     -> SALE at the location the parcel leaves from (default: the reserving warehouse). Strict:
               refuses when the location doesn't have the units, so stock never goes negative. The
               reservation is released in the same step.
  * cancel   -> RELEASE of whatever is still reserved (before shipping), or RETURN of shipped units
               (a formal cancellation after the parcel left).
  * return   -> RETURN of received units to the location they were shipped from.

The storefront reads `inventory.WarehouseInventoryModel` as "sellable"; move() mirrors on-hand changes
into it, and this module mirrors reservations too, so a confirmed-but-not-shipped order already
stops the storefront from selling the same units twice.
"""
from __future__ import annotations

import logging
from collections import defaultdict

from django.db.models import Sum

from apps.stores.infrastructure import stock_service
from apps.stores.infrastructure.models import StockMovement, StockMovementType, Store, StoreKind, StoreStatus

logger = logging.getLogger("nutrizone.app")


def fulfilment_store() -> Store | None:
    """The main warehouse online orders are packed from (the oldest active one)."""
    return Store.objects.filter(kind=StoreKind.WAREHOUSE, status=StoreStatus.ACTIVE).order_by("created_at").first()


def ship_locations():
    """Locations a parcel may leave from: warehouses first, then active branches."""
    return Store.objects.filter(status=StoreStatus.ACTIVE).order_by("-kind", "name")  # "warehouse" > "store"


def _ledger(order_number: str, movement_type: str):
    return StockMovement.objects.filter(reference=order_number, movement_type=movement_type)


def reserved_for(order_number: str) -> dict:
    """{(store_id, variant_id): units still reserved for this order}."""
    out: dict = defaultdict(int)
    for row in _ledger(order_number, StockMovementType.RESERVATION).values("store_id", "product_variant_id").annotate(n=Sum("quantity")):
        out[(row["store_id"], row["product_variant_id"])] += row["n"]
    for row in _ledger(order_number, StockMovementType.RELEASE).values("store_id", "product_variant_id").annotate(n=Sum("quantity")):
        out[(row["store_id"], row["product_variant_id"])] += row["n"]  # move() records a release as negative units
    return {k: v for k, v in out.items() if v > 0}


def shipped_from(order_number: str) -> dict:
    """{(store_id, variant_id): units shipped and not yet returned}."""
    out: dict = defaultdict(int)
    for row in _ledger(order_number, StockMovementType.SALE).values("store_id", "product_variant_id").annotate(n=Sum("quantity")):
        out[(row["store_id"], row["product_variant_id"])] += -row["n"]  # SALE rows are negative
    for row in _ledger(order_number, StockMovementType.RETURN).values("store_id", "product_variant_id").annotate(n=Sum("quantity")):
        out[(row["store_id"], row["product_variant_id"])] -= row["n"]
    return {k: v for k, v in out.items() if v > 0}


def _mirror_reserve(store_id, variant_id, units: int, reference: str) -> None:
    # Reserved units are not sellable: the storefront mirror shows quantity - reserved.
    stock_service._mirror_inventory(store_id, variant_id, -units, reference)


def reserve(order_number: str, lines: list[tuple], actor: str = "") -> list[dict]:
    """lines = [(variant_id, qty)]. Reserves what is free at the order's branch (pickup / assigned) or else the
    fulfilment warehouse; returns the shortages."""
    from apps.stores.infrastructure.store_orders import assigned_store

    store = assigned_store(order_number) or fulfilment_store()
    if store is None:
        return [{"variant_id": vid, "short": qty} for vid, qty in lines]
    already = reserved_for(order_number)
    free = stock_service.available_map(store, [vid for vid, _ in lines])
    shortages = []
    for vid, qty in lines:
        want = qty - already.get((store.id, vid), 0)
        take = max(0, min(want, free.get(vid, 0)))
        if take:
            stock_service.move(store, vid, 0, StockMovementType.RESERVATION, reserve=take, reference=order_number, actor=actor, note="Online order reserved")
            _mirror_reserve(store.id, vid, take, order_number)
        if want - take > 0:
            shortages.append({"variant_id": vid, "short": want - take})
    return shortages


def release(order_number: str, lines: list[tuple] | None = None, actor: str = "", note: str = "Online order cancelled") -> int:
    """Gives back reserved units: all of them, or up to qty per variant for lines = [(variant_id, qty)]. Returns the units released."""
    limits = None if lines is None else {}
    for vid, qty in lines or []:
        limits[vid] = limits.get(vid, 0) + qty
    released = 0
    for (store_id, vid), units in reserved_for(order_number).items():
        if limits is not None:
            units = min(units, limits.get(vid, 0))
            if units <= 0:
                continue
            limits[vid] -= units
        store = Store.objects.get(pk=store_id)
        stock_service.move(store, vid, 0, StockMovementType.RELEASE, reserve=-units, reference=order_number, actor=actor, note=note)
        _mirror_reserve(store_id, vid, -units, order_number)
        released += units
    return released


def shortages_at(store: Store, order_number: str, lines: list[tuple]) -> list[dict]:
    """What shipping these lines from `store` would be missing (units this order reserved there count as available)."""
    reserved = reserved_for(order_number)
    free = stock_service.available_map(store, [vid for vid, _ in lines])
    out = []
    for vid, qty in lines:
        have = free.get(vid, 0) + reserved.get((store.id, vid), 0)
        if have < qty:
            out.append({"variant_id": vid, "need": qty, "have": have})
    return out


def ship(order_number: str, lines: list[tuple], store: Store | None = None, actor: str = "") -> Store | None:
    """Takes the units off the shelf at `store` (default: where they were reserved, else the main warehouse). Strict."""
    reserved = reserved_for(order_number)
    if store is None:
        reserving = {sid for (sid, _vid) in reserved}
        store = Store.objects.filter(pk__in=reserving).first() if len(reserving) == 1 else None
        store = store or fulfilment_store()
    if store is None:
        return None  # no warehouse configured at all: this shop doesn't track location stock for online orders
    missing = shortages_at(store, order_number, lines)
    if missing:
        raise stock_service.conflict("INSUFFICIENT_STOCK", f"Not enough stock at {store.name}.", store=store.name, lines=[{**m, "variant_id": str(m["variant_id"])} for m in missing])
    for vid, qty in lines:
        here = reserved.pop((store.id, vid), 0)
        use = min(here, qty)
        if use:  # release first, then sell: the ledger shows both steps and reserved_for() stays exact
            stock_service.move(store, vid, 0, StockMovementType.RELEASE, reserve=-use, reference=order_number, actor=actor, note="Reserved units shipped")
            _mirror_reserve(store.id, vid, -use, order_number)
        stock_service.move(store, vid, -qty, StockMovementType.SALE, reference=order_number, actor=actor, note="Online order shipped")
        if here > use:  # reserved more than is being shipped (e.g. a line was reduced) -- free the rest
            stock_service.move(store, vid, 0, StockMovementType.RELEASE, reserve=-(here - use), reference=order_number, actor=actor, note="Not shipped")
            _mirror_reserve(store.id, vid, -(here - use), order_number)
    # Reservations held elsewhere (shipped from another location) are no longer needed.
    for (sid, vid), units in reserved.items():
        loc = Store.objects.get(pk=sid)
        stock_service.move(loc, vid, 0, StockMovementType.RELEASE, reserve=-units, reference=order_number, actor=actor, note=f"Shipped from {store.name}")
        _mirror_reserve(sid, vid, -units, order_number)
    return store


def restock(order_number: str, lines: list[tuple], actor: str = "", note: str = "Online order returned") -> int:
    """Puts shipped units back where they left from (only what was actually shipped). Returns the units restocked."""
    out = shipped_from(order_number)
    done = 0
    for vid, qty in lines:
        left = qty
        for (sid, v), units in out.items():
            if v != vid or left <= 0:
                continue
            take = min(units, left)
            stock_service.move(Store.objects.get(pk=sid), vid, take, StockMovementType.RETURN, reference=order_number, actor=actor, note=note)
            out[(sid, v)] -= take
            left -= take
            done += take
    return done


class StoresStockBridge:
    """Implements ordering's OrderStockPort on top of this module (wired in ordering/infrastructure/composition.py)."""

    def __init__(self, actor: str = "") -> None:
        self.actor = actor

    def reserve(self, order_number, lines):
        try:
            return reserve(order_number, lines, self.actor)
        except Exception:  # noqa: BLE001 - a reservation problem never blocks confirming an order
            logger.exception("online fulfilment: reserve failed for %s", order_number)
            return []

    def release(self, order_number, lines=None):
        return release(order_number, lines, self.actor)

    def ship(self, order_number, lines, store_id=None):
        store = Store.objects.filter(pk=store_id).first() if store_id else None
        if store_id and store is None:
            raise stock_service.conflict("NO_FULFILMENT_LOCATION", "Unknown location.")
        return ship(order_number, lines, store, self.actor)

    def restock(self, order_number, lines):
        return restock(order_number, lines, self.actor)

    def has_shipped(self, order_number) -> bool:
        return bool(shipped_from(order_number))
