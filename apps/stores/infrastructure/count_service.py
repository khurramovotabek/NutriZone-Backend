"""
Stock count (Inventarizatsiya) -- comparing what the system says a location holds with what is on the shelf.

    start ──▶ COUNTING ──submit──▶ REVIEW ──post──▶ POSTED
                 ▲                    │
                 └──────recount───────┘          (COUNTING / REVIEW ──cancel──▶ CANCELLED)

* start      a full count lists every product with stock at the location; a partial count only the chosen ones.
             Each line snapshots `expected_quantity` (system on-hand) at that moment. A product scanned during
             the count that wasn't listed is added with its live on-hand as the expectation.
* counting   counts are absolute per line (re-sending is harmless, several counters can work in parallel).
             A blind count hides the expectation from the counting screen.
* submit     every line must be counted -- or `uncounted_as_zero` (a full count: what wasn't found isn't there).
* review     a reason is required for every difference; the value impact is shown at cost.
* post       each difference (counted − expected) is applied to the *live* stock as one ledger row
             (sales made during the count stay correct). A shortage that would push stock below what is
             reserved is clamped and the actually-posted change is recorded on the line.
Every step locks the count row; posting runs in one transaction with stock_service.move().
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.stores.infrastructure import stock_service as stock
from apps.stores.infrastructure.models import (
    CountReason,
    StockCount,
    StockCountItem,
    StockCountScope,
    StockCountStatus,
    StockMovementType,
    Store,
    StoreProductStock,
)
from common.exceptions import ResourceNotFound, ValidationFailed

S = StockCountStatus
# shortages with these reasons are booked as their own movement type, so reports can tell them apart
SHORTAGE_MOVEMENT = {CountReason.DAMAGED: StockMovementType.DAMAGE, CountReason.EXPIRED: StockMovementType.EXPIRED}


COST_RECEIPT, COST_CATALOG, COST_PRICE = "receipt", "catalog", "price"


def cost_info(variant_ids) -> dict:
    """
    {variant_id: (unit cost, source)} -- the best known purchase cost per variant:
      receipt  the latest goods receipt (Kirim) that carried a unit cost -- the real, current purchase price;
      catalog  the cost price typed on the variant / price list (cost_price_amount);
      price    nothing better known: the selling price stands in (valuation is then an estimate);
      None     no cost and no price at all (0).
    """
    from apps.pricing.infrastructure.models import PriceListEntryModel
    from apps.stores.infrastructure.models import StockReceiptItem

    ids = list({v for v in variant_ids if v})
    out: dict = {}
    for row in StockReceiptItem.objects.filter(product_variant_id__in=ids, unit_cost__isnull=False, unit_cost__gt=0).order_by("product_variant_id", "-receipt__created_at").values("product_variant_id", "unit_cost"):
        out.setdefault(row["product_variant_id"], (row["unit_cost"], COST_RECEIPT))
    missing = [v for v in ids if v not in out]
    if missing:
        rows = PriceListEntryModel.objects.filter(product_variant_id__in=missing, cost_price_amount__gt=0, price_list__status="active").order_by("product_variant_id", "price_list__created_at")
        for vid, cost in rows.values_list("product_variant_id", "cost_price_amount"):
            out.setdefault(vid, (cost, COST_CATALOG))
    missing = [v for v in ids if v not in out]
    if missing:
        infos = stock.variant_infos(missing)
        for v in missing:
            info = infos.get(v)
            out[v] = (info.price, COST_PRICE) if info and info.price is not None else (Decimal(0), None)
    return out


def cost_map(variant_ids) -> dict:
    """Best known unit cost per variant (see cost_info): latest receipt cost, else catalog cost price, else selling price, else 0."""
    return {v: cost for v, (cost, _src) in cost_info(variant_ids).items()}


def _locked(count_id) -> StockCount:
    c = StockCount.objects.select_for_update().select_related("store").filter(id=count_id).first()
    if c is None:
        raise ResourceNotFound("Stock count not found.")
    return c


def _require(c: StockCount, *statuses) -> None:
    if c.status not in statuses:
        raise stock.conflict("INVALID_STATE", f"This step isn't possible while the count is '{c.get_status_display()}'.", status=c.status)


def _add_lines(c: StockCount, variant_ids, added_during: bool) -> list[StockCountItem]:
    already = set(c.items.values_list("product_variant_id", flat=True))
    ids = [v for v in dict.fromkeys(variant_ids) if v not in already]
    if not ids:
        return []
    infos = stock.variant_infos(ids)
    if len(infos) != len(ids):
        raise ResourceNotFound("One of the products doesn't exist.")
    on_hand = dict(StoreProductStock.objects.filter(store=c.store, product_variant_id__in=ids).values_list("product_variant_id", "quantity"))
    costs = cost_map(ids)
    made = []
    for vid in ids:
        info = infos[vid]
        made.append(StockCountItem.objects.create(
            count=c, product_variant_id=vid, name=info.name[:255], sku=info.sku[:64], barcode=(info.barcode or "")[:64],
            expected_quantity=on_hand.get(vid, 0), unit_cost=costs.get(vid) or 0, added_during_count=added_during,
        ))
    return made


def start(store_id, actor: str, scope: str = StockCountScope.FULL, blind: bool = True, note: str = "", variant_ids=None) -> StockCount:
    try:
        store = Store.objects.get(id=uuid.UUID(str(store_id)))
    except (ValueError, TypeError, Store.DoesNotExist) as exc:
        raise ResourceNotFound("Choose a location.") from exc
    if scope not in StockCountScope.values:
        raise ValidationFailed("Unknown count scope.")
    if StockCount.objects.filter(store=store, status__in=(S.COUNTING, S.REVIEW)).exists():
        raise stock.conflict("COUNT_IN_PROGRESS", f"A stock count is already open at {store.name}. Finish or cancel it first.", store=store.name)
    with transaction.atomic():
        c = StockCount.objects.create(
            number=stock.next_number("IC", "stores_count_number_seq"), store=store, scope=scope, blind=bool(blind),
            note=(note or "")[:255], created_by=actor[:150],
        )
        if scope == StockCountScope.FULL:
            ids = list(StoreProductStock.objects.filter(store=store).filter(Q(quantity__gt=0) | Q(reserved_quantity__gt=0)).values_list("product_variant_id", flat=True))
        else:
            ids = [uuid.UUID(str(v)) for v in (variant_ids or [])]
            if not ids:
                raise stock.conflict("EMPTY_COUNT", "Choose at least one product to count.")
        _add_lines(c, ids, added_during=False)
    return c


def add_products(count_id, actor: str, variant_ids) -> list[StockCountItem]:
    """Products found on the shelf that weren't on the list (scanned during the count)."""
    with transaction.atomic():
        c = _locked(count_id)
        _require(c, S.COUNTING)
        return _add_lines(c, [uuid.UUID(str(v)) for v in variant_ids], added_during=True)


def save_counts(count_id, actor: str, counts: dict) -> StockCount:
    """{item_id: quantity | None} -- absolute counts (None clears a line back to 'not counted')."""
    now = timezone.now()
    with transaction.atomic():
        c = _locked(count_id)
        _require(c, S.COUNTING)
        items = {str(i.id): i for i in c.items.all()}
        for item_id, raw in (counts or {}).items():
            item = items.get(str(item_id))
            if item is None:
                raise ResourceNotFound("That product is not on this count.")
            if raw in (None, ""):
                qty = None
            else:
                try:
                    qty = int(raw)
                except (TypeError, ValueError) as exc:
                    raise ValidationFailed("Counts must be whole numbers.") from exc
                if qty < 0 or qty > stock.MAX_UNITS_PER_LINE:
                    raise ValidationFailed("A count can't be negative or that large.")
            if qty != item.counted_quantity:
                StockCountItem.objects.filter(pk=item.pk).update(counted_quantity=qty, counted_by=actor[:150] if qty is not None else "", counted_at=now if qty is not None else None)
    return c


def submit(count_id, actor: str, uncounted_as_zero: bool = False) -> StockCount:
    with transaction.atomic():
        c = _locked(count_id)
        _require(c, S.COUNTING)
        uncounted = c.items.filter(counted_quantity__isnull=True)
        if uncounted.exists():
            if not uncounted_as_zero:
                raise stock.conflict("UNCOUNTED_LINES", f"{uncounted.count()} product(s) are not counted yet.", lines=uncounted.count(), names=list(uncounted.values_list("name", flat=True)[:10]))
            uncounted.update(counted_quantity=0, counted_by=actor[:150], counted_at=timezone.now())
        c.status, c.submitted_by, c.submitted_at = S.REVIEW, actor[:150], timezone.now()
        c.save(update_fields=["status", "submitted_by", "submitted_at"])
    return c


def recount(count_id, actor: str) -> StockCount:
    with transaction.atomic():
        c = _locked(count_id)
        _require(c, S.REVIEW)
        c.status = S.COUNTING
        c.save(update_fields=["status"])
    return c


def save_reasons(count_id, actor: str, reasons: dict) -> StockCount:
    """{item_id: {reason, note}} for lines with a difference."""
    with transaction.atomic():
        c = _locked(count_id)
        _require(c, S.REVIEW, S.COUNTING)
        items = {str(i.id): i for i in c.items.all()}
        for item_id, r in (reasons or {}).items():
            item = items.get(str(item_id))
            if item is None:
                continue
            code = (r or {}).get("reason") or ""
            if code and code not in CountReason.values:
                raise ValidationFailed("Unknown reason.")
            StockCountItem.objects.filter(pk=item.pk).update(reason=code, note=str((r or {}).get("note") or "")[:255])
    return c


def post(count_id, actor: str) -> StockCount:
    """Applies every difference to the live stock (one ledger row each) and freezes the count as a report."""
    with transaction.atomic():
        c = _locked(count_id)
        _require(c, S.REVIEW)
        items = list(c.items.all())
        missing = [i.name for i in items if i.difference and not i.reason]
        if missing:
            raise stock.conflict("REASON_REQUIRED", "Give a reason for every difference.", products=missing[:20])
        shortage_units = excess_units = matched = 0
        shortage_value = excess_value = Decimal(0)
        for i in items:
            diff = i.difference
            if diff == 0:
                matched += 1
                continue
            row = StoreProductStock.objects.filter(store=c.store, product_variant_id=i.product_variant_id).first()
            live, reserved = (row.quantity, row.reserved_quantity) if row else (0, 0)
            apply = diff if diff > 0 else max(diff, -(live - reserved))  # never below what's reserved for orders / transfers
            if apply:
                kind = SHORTAGE_MOVEMENT.get(i.reason, StockMovementType.ADJUSTMENT) if apply < 0 else StockMovementType.ADJUSTMENT
                note = f"Inventarizatsiya: {CountReason(i.reason).label}" + (f" — {i.note}" if i.note else "")
                stock.move(c.store, i.product_variant_id, apply, kind, reference=c.number, actor=actor, note=note, document_id=c.id)
            StockCountItem.objects.filter(pk=i.pk).update(adjusted_quantity=apply)
            if diff < 0:
                shortage_units += -diff
                shortage_value += i.unit_cost * -diff
            else:
                excess_units += diff
                excess_value += i.unit_cost * diff
        c.status, c.posted_by, c.posted_at = S.POSTED, actor[:150], timezone.now()
        c.lines_total, c.lines_matched = len(items), matched
        c.shortage_units, c.excess_units, c.shortage_value, c.excess_value = shortage_units, excess_units, shortage_value, excess_value
        c.save()
    return c


def cancel(count_id, actor: str, reason: str = "") -> StockCount:
    with transaction.atomic():
        c = _locked(count_id)
        _require(c, S.COUNTING, S.REVIEW)
        c.status, c.cancelled_by, c.cancelled_at, c.cancel_reason = S.CANCELLED, actor[:150], timezone.now(), (reason or "")[:255]
        c.save(update_fields=["status", "cancelled_by", "cancelled_at", "cancel_reason"])
    return c


def summary(c: StockCount) -> dict:
    items = list(c.items.all())
    counted = [i for i in items if i.counted_quantity is not None]
    diffs = [i for i in counted if i.difference]
    short = [i for i in diffs if i.difference < 0]
    excess = [i for i in diffs if i.difference > 0]
    return {
        "lines": len(items), "counted": len(counted), "progress": round(len(counted) * 100 / len(items)) if items else 0,
        "matched": len(counted) - len(diffs), "differences": len(diffs),
        "expected_units": sum(i.expected_quantity for i in items), "counted_units": sum(i.counted_quantity or 0 for i in counted),
        "shortage_units": sum(-i.difference for i in short), "excess_units": sum(i.difference for i in excess),
        "shortage_value": sum((i.unit_cost * -i.difference for i in short), Decimal(0)),
        "excess_value": sum((i.unit_cost * i.difference for i in excess), Decimal(0)),
        "accuracy": round((len(counted) - len(diffs)) * 100 / len(counted)) if counted else 0,
        "missing_reasons": sum(1 for i in diffs if not i.reason),
    }
