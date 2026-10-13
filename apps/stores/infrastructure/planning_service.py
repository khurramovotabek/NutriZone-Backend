"""
Stock planning: reorder points / replenishment, and the expiry (FEFO) view.

Replenishment (Minimal qoldiq → To'ldirish)
    per product at a location:  projected = available (on hand − reserved) + incoming (open transfers to it)
    it needs replenishing when projected <= min; the suggestion fills it up to `target`, capped by what the
    source (normally the main warehouse) has available. Sales speed over the last SALES_DAYS days gives
    "days of cover" and a suggested rule (min = SAFETY_DAYS of sales, target = COVER_DAYS of sales) for
    products that sell but have no rule yet. A suggestion becomes a transfer draft in one click.

Expiry (Yaroqlilik muddati)
    Stock is tracked per batch (StockBatch): receipts bring batch + expiry, outgoing units leave the batch that
    expires first (FEFO), transfers carry their batches to the destination. Units received without a batch
    are "no expiry recorded".
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.stores.infrastructure import stock_service as stock
from apps.stores.infrastructure.models import (
    ReorderRule,
    StockMovement,
    StockMovementType,
    StockTransfer,
    Store,
    StoreKind,
    StoreProductStock,
    TransferStatus,
)
from common.exceptions import ResourceNotFound, ValidationFailed

SALES_DAYS = 30
SAFETY_DAYS = 7
COVER_DAYS = 21
OPEN_TRANSFERS = (TransferStatus.DRAFT, TransferStatus.READY, TransferStatus.IN_TRANSIT, TransferStatus.RECEIVING, TransferStatus.PARTIALLY_RECEIVED)
EXPIRY_BUCKETS = ((30, "d30"), (60, "d60"), (90, "d90"))  # days left <= n (below 0: "expired")


def default_source(exclude=None) -> Store | None:
    qs = Store.objects.filter(kind=StoreKind.WAREHOUSE).exclude(status="inactive").order_by("name")
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.first()


# ---------------------------------------------------------------- replenishment


def incoming_map(store: Store, variant_ids=None) -> dict:
    """Units already on their way to `store`: drafts / ready (planned) + in transit (sent, not yet posted)."""
    from apps.stores.infrastructure.models import StockTransferItem

    qs = StockTransferItem.objects.filter(transfer__destination=store, transfer__status__in=OPEN_TRANSFERS)
    if variant_ids is not None:
        qs = qs.filter(product_variant_id__in=list(variant_ids))
    out: dict = {}
    for i in qs.values("product_variant_id", "expected_quantity", "dispatched_quantity", "received_posted", "transfer__status"):
        if i["transfer__status"] in (TransferStatus.DRAFT, TransferStatus.READY):
            units = i["expected_quantity"]
        else:
            units = max(0, i["dispatched_quantity"] - i["received_posted"])
        out[i["product_variant_id"]] = out.get(i["product_variant_id"], 0) + units
    return out


def sales_map(store: Store, days: int = SALES_DAYS) -> dict:
    """Units sold per product at `store` in the last `days` days (sales minus customer returns)."""
    since = timezone.now() - timedelta(days=days)
    rows = StockMovement.objects.filter(store=store, created_at__gte=since, movement_type__in=(StockMovementType.SALE, StockMovementType.RETURN))
    out: dict = {}
    for r in rows.values("product_variant_id", "movement_type").annotate(q=Sum("quantity")):
        out[r["product_variant_id"]] = out.get(r["product_variant_id"], 0) - r["q"]  # sales are negative, returns positive
    return {k: max(0, v) for k, v in out.items()}


def suggested_rule(sold: int, days: int = SALES_DAYS) -> tuple[int, int]:
    per_day = sold / days if days else 0
    low = max(1, math.ceil(per_day * SAFETY_DAYS))
    return low, max(low + 1, math.ceil(per_day * COVER_DAYS))


@dataclass
class Line:
    variant_id: uuid.UUID
    info: object
    rule: ReorderRule | None
    on_hand: int
    reserved: int
    incoming: int
    source_available: int
    sold: int

    @property
    def available(self) -> int:
        return max(0, self.on_hand - self.reserved)

    @property
    def projected(self) -> int:
        return self.available + self.incoming

    @property
    def per_day(self) -> float:
        return self.sold / SALES_DAYS

    @property
    def days_cover(self) -> int | None:
        return int(self.available / self.per_day) if self.per_day else None

    @property
    def needs(self) -> bool:
        return bool(self.rule) and self.projected <= self.rule.min_quantity

    @property
    def suggest(self) -> int:
        return max(0, self.rule.target_quantity - self.projected) if self.needs else 0

    @property
    def can_send(self) -> int:
        return min(self.suggest, self.source_available)

    @property
    def state(self) -> str:
        if not self.rule:
            return "norule"
        if self.available == 0:
            return "out"
        return "need" if self.needs else "ok"


def plan(store: Store, source: Store | None) -> dict:
    """Every product with a rule at `store` + products that sold there without a rule (rule suggestions)."""
    rules = {r.product_variant_id: r for r in ReorderRule.objects.filter(store=store)}
    sold = sales_map(store)
    ids = set(rules) | {v for v, q in sold.items() if q > 0}
    stock_rows = {r["product_variant_id"]: r for r in StoreProductStock.objects.filter(store=store, product_variant_id__in=ids).values("product_variant_id", "quantity", "reserved_quantity")}
    incoming = incoming_map(store, ids)
    src = stock.available_map(source, ids) if source else {}
    infos = stock.variant_infos(ids)
    lines = []
    for vid in ids:
        if vid not in infos:
            continue
        row = stock_rows.get(vid) or {"quantity": 0, "reserved_quantity": 0}
        lines.append(Line(vid, infos[vid], rules.get(vid), row["quantity"], row["reserved_quantity"], incoming.get(vid, 0), src.get(vid, 0), sold.get(vid, 0)))
    lines.sort(key=lambda ln: ({"out": 0, "need": 1, "ok": 2, "norule": 3}[ln.state], -(ln.suggest or 0), ln.info.name))
    return {"lines": lines, "need": [ln for ln in lines if ln.needs], "norule": [ln for ln in lines if not ln.rule]}


def transfer_suggestions(store: Store, source: Store, limit: int = 60) -> list[dict]:
    """
    What a new transfer source → store should carry: products under their minimum at `store` (filled up to the
    rule's target) and products that sell there without a rule (filled up to the suggested rule), each capped by
    what `source` has free. Ordered: out of stock first, then the biggest gap.
    """
    out = []
    for ln in plan(store, source)["lines"]:
        if ln.rule:
            low, target, why = ln.rule.min_quantity, ln.rule.target_quantity, "rule"
        else:
            low, target = suggested_rule(ln.sold)
            why = "sales"
        if ln.projected > low:
            continue
        want = max(0, target - ln.projected)
        send = min(want, ln.source_available)
        if send <= 0:
            continue
        out.append({
            "variant_id": str(ln.variant_id), "name": ln.info.name, "sku": ln.info.sku, "size": ln.info.size, "image_url": ln.info.image_url,
            "available": ln.available, "incoming": ln.incoming, "min": low, "target": target, "sold": ln.sold, "days_cover": ln.days_cover,
            "source_available": ln.source_available, "want": want, "suggest": send, "why": why, "out": ln.available == 0,
        })
    out.sort(key=lambda r: (not r["out"], -(r["want"] - r["available"]), r["name"]))
    return out[:limit]


def overview() -> dict:
    """Location id -> {"rules", "need", "out"} for the location cards."""
    out: dict = {}
    for store in Store.objects.exclude(status="inactive"):
        rules = list(ReorderRule.objects.filter(store=store))
        if not rules:
            out[store.id] = {"rules": 0, "need": 0, "out": 0}
            continue
        ids = [r.product_variant_id for r in rules]
        avail = stock.available_map(store, ids)
        incoming = incoming_map(store, ids)
        need = sum(1 for r in rules if avail.get(r.product_variant_id, 0) + incoming.get(r.product_variant_id, 0) <= r.min_quantity)
        out[store.id] = {"rules": len(rules), "need": need, "out": sum(1 for r in rules if avail.get(r.product_variant_id, 0) == 0)}
    return out


def save_rules(store: Store, actor: str, rules: dict) -> int:
    """{variant_id: {"min": n, "target": m} | None} -- None (or both empty) removes the rule."""
    saved = 0
    with transaction.atomic():
        for vid, r in (rules or {}).items():
            try:
                vid = uuid.UUID(str(vid))
            except ValueError as exc:
                raise ValidationFailed("Unknown product.") from exc
            if not r or (r.get("min") in (None, "") and r.get("target") in (None, "")):
                ReorderRule.objects.filter(store=store, product_variant_id=vid).delete()
                continue
            try:
                low, target = int(r.get("min") or 0), int(r.get("target") or 0)
            except (TypeError, ValueError) as exc:
                raise ValidationFailed("Minimum and target must be whole numbers.") from exc
            if low < 0 or target <= 0 or target < low or target > stock.MAX_UNITS_PER_LINE:
                raise ValidationFailed("The fill-up quantity must be positive and not below the minimum.")
            ReorderRule.objects.update_or_create(store=store, product_variant_id=vid, defaults={"min_quantity": low, "target_quantity": target, "updated_by": actor[:150]})
            saved += 1
    return saved


def create_transfer(store: Store, source: Store, actor: str, quantities: dict) -> StockTransfer:
    """{variant_id: units} -> a transfer DRAFT source → store (validated against the source's stock by update_draft)."""
    from apps.stores.infrastructure import transfer_service

    lines = [{"variant_id": str(v), "quantity": int(q)} for v, q in (quantities or {}).items() if q and int(q) > 0]
    if not lines:
        raise stock.conflict("EMPTY_TRANSFER", "Nothing to send.")
    with transaction.atomic():
        t = transfer_service.create(source.id, store.id, actor, notes="Minimal qoldiq bo'yicha to'ldirish")
        transfer_service.update_draft(t.id, actor, lines)
    return t


# ---------------------------------------------------------------- expiry


INCOMING_TYPES = (StockMovementType.RECEIPT, StockMovementType.TRANSFER_IN, StockMovementType.RETURN, StockMovementType.ADJUSTMENT)


@dataclass
class Layer:
    store_id: uuid.UUID
    variant_id: uuid.UUID
    quantity: int
    batch: str
    expiry: date | None
    received: object

    def days_left(self, today: date) -> int | None:
        return (self.expiry - today).days if self.expiry else None


def layers(store_ids=None) -> list[Layer]:
    """The batches on the shelf (StockBatch, kept exact by stock_service.move())."""
    from apps.stores.infrastructure.models import StockBatch

    qs = StockBatch.objects.filter(quantity__gt=0)
    if store_ids is not None:
        qs = qs.filter(store_id__in=list(store_ids))
    return [Layer(b["store_id"], b["product_variant_id"], b["quantity"], b["batch_number"], b["expiry_date"], b["received_at"])
            for b in qs.values("store_id", "product_variant_id", "quantity", "batch_number", "expiry_date", "received_at")]


def estimated_layers(store_ids=None) -> list[Layer]:
    """The FIFO estimate used before batch tracking: on-hand attributed to the newest incoming movements of each product."""
    qs = StoreProductStock.objects.filter(quantity__gt=0)
    if store_ids is not None:
        qs = qs.filter(store_id__in=list(store_ids))
    on_hand = {(r["store_id"], r["product_variant_id"]): r["quantity"] for r in qs.values("store_id", "product_variant_id", "quantity")}
    if not on_hand:
        return []
    moves = StockMovement.objects.filter(movement_type__in=INCOMING_TYPES, quantity__gt=0, store_id__in={k[0] for k in on_hand},
                                         product_variant_id__in={k[1] for k in on_hand}).order_by("-created_at")
    left = dict(on_hand)
    out: dict = {}
    for m in moves.values("store_id", "product_variant_id", "quantity", "batch_number", "expiry_date", "created_at").iterator():
        key = (m["store_id"], m["product_variant_id"])
        need = left.get(key, 0)
        if need <= 0:
            continue
        take = min(need, m["quantity"])
        left[key] = need - take
        lk = (key, m["batch_number"] or "", m["expiry_date"])
        if lk in out:
            out[lk].quantity += take
        else:
            out[lk] = Layer(key[0], key[1], take, m["batch_number"] or "", m["expiry_date"], m["created_at"])
    for key, rest in left.items():  # stock older than the ledger (opening balances): no batch info
        if rest > 0:
            lk = (key, "", None)
            if lk in out:
                out[lk].quantity += rest
            else:
                out[lk] = Layer(key[0], key[1], rest, "", None, None)
    return list(out.values())


def bucket(days_left: int | None) -> str:
    if days_left is None:
        return "unknown"
    if days_left < 0:
        return "expired"
    return next((name for limit, name in EXPIRY_BUCKETS if days_left <= limit), "ok")


def expiry_report(store_ids=None, today: date | None = None) -> dict:
    today = today or timezone.localdate()
    all_layers = layers(store_ids)
    dated = [ly for ly in all_layers if ly.expiry]
    by_product: dict = {}
    for ly in dated:
        if ly.expiry < today:
            continue  # expired stock is written off, not sold -- FEFO is about the sellable batches
        by_product.setdefault((ly.store_id, ly.variant_id), []).append(ly)
    fefo = {}  # (store, variant) -> the batch to sell first, when more than one expiry is on the shelf
    for key, group in by_product.items():
        expiries = sorted({ly.expiry for ly in group})
        if len(expiries) > 1:
            first = min(group, key=lambda ly: ly.expiry)
            fefo[key] = first
    return {
        "today": today, "layers": dated, "fefo": fefo,
        "unknown_units": sum(ly.quantity for ly in all_layers if not ly.expiry),
        "unknown_products": len({(ly.store_id, ly.variant_id) for ly in all_layers if not ly.expiry}),
    }


def location(store_id) -> Store:
    try:
        return Store.objects.get(id=uuid.UUID(str(store_id)))
    except (ValueError, TypeError, Store.DoesNotExist) as exc:
        raise ResourceNotFound("Location not found.") from exc

