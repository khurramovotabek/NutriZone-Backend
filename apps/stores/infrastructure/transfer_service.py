"""
Inventory transfers between locations (warehouse → branch, branch → branch) -- the workflow of an ERP/WMS:

    DRAFT ──ready──▶ READY ──dispatch──▶ IN_TRANSIT ──count──▶ RECEIVING ──confirm──▶ RECEIVED ──complete──▶ COMPLETED
      │                │                                           │   ▲
      │                └──back to draft (releases the reservation) ▼   │ approve discrepancy
      └──cancel──▶ CANCELLED ◀──cancel── READY          PARTIALLY_RECEIVED (partial posting or shortage/excess awaiting approval)

Stock accounting (every step a ledger row via stock_service.move):
    READY        source: units reserved (RESERVATION) -- still on hand, no longer sellable
    dispatch     source: reservation released, picked units leave (TRANSFER_OUT); they are "in transit" on the document
    receipt      destination: counted units arrive (TRANSFER_IN), posted in one or more receipts
    approval     shortage: written off (lost in transit) or returned to the source (never left);
                 excess:   deducted from the source (it was sent unrecorded) or accepted as found
All state changes lock the transfer row (select_for_update) and validate the current status, so a
double click or two operators never apply a step twice. Quantities are sent as absolute counts
(not increments), which makes re-submitting a scan idempotent.
"""
from __future__ import annotations

import uuid
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.stores.infrastructure import stock_service as stock
from apps.stores.infrastructure.models import (
    DiscrepancyReason,
    StockMovementType,
    StockTransfer,
    StockTransferEvent,
    StockTransferItem,
    Store,
    StoreKind,
    TransferStatus,
)
from common.exceptions import ResourceNotFound, ValidationFailed

S = TransferStatus
ALLOWED = {
    S.DRAFT: {S.READY, S.CANCELLED},
    S.READY: {S.DRAFT, S.IN_TRANSIT, S.CANCELLED},
    S.IN_TRANSIT: {S.RECEIVING, S.PARTIALLY_RECEIVED, S.RECEIVED},
    S.RECEIVING: {S.PARTIALLY_RECEIVED, S.RECEIVED},
    S.PARTIALLY_RECEIVED: {S.RECEIVING, S.PARTIALLY_RECEIVED, S.RECEIVED},
    S.RECEIVED: {S.COMPLETED},
    S.COMPLETED: set(),
    S.CANCELLED: set(),
}
RECEIVABLE = (S.IN_TRANSIT, S.RECEIVING, S.PARTIALLY_RECEIVED)
SHORTAGE_RESOLUTIONS = ("write_off", "return_to_source")
EXCESS_RESOLUTIONS = ("deduct_source", "accept")


def _event(t: StockTransfer, action: str, message: str, actor: str, old=None, new=None) -> None:
    StockTransferEvent.objects.create(transfer=t, action=action, message=message[:300], actor=actor[:150], old_value=old, new_value=new)


def _locked(transfer_id) -> StockTransfer:
    t = StockTransfer.objects.select_for_update().select_related("source", "destination").filter(id=transfer_id).first()
    if t is None:
        raise ResourceNotFound("Transfer not found.")
    return t


def _go(t: StockTransfer, target: str, actor: str, message: str) -> None:
    if target not in ALLOWED[TransferStatus(t.status)]:
        raise stock.conflict("INVALID_TRANSITION", f"A transfer in status '{t.get_status_display()}' can't become '{TransferStatus(target).label}'.", status=t.status)
    old = t.status
    t.status = target
    _event(t, f"status:{target}", message, actor, {"status": old}, {"status": target})


def _stores(source_id, destination_id) -> tuple[Store, Store]:
    try:
        sid, did = uuid.UUID(str(source_id)), uuid.UUID(str(destination_id))
    except (TypeError, ValueError) as exc:
        raise ValidationFailed("Choose both locations.") from exc
    if sid == did:
        raise stock.conflict("SAME_LOCATION", "The source and destination can't be the same location.")
    stores = {s.id: s for s in Store.objects.filter(id__in=[sid, did])}
    if len(stores) != 2:
        raise ResourceNotFound("Location not found.")
    return stores[sid], stores[did]


# ---------------------------------------------------------------- draft


def create(source_id, destination_id, actor: str, notes: str = "") -> StockTransfer:
    source, destination = _stores(source_id, destination_id)
    with transaction.atomic():
        t = StockTransfer.objects.create(
            number=stock.next_number("TR", "stores_transfer_number_seq"), source=source, destination=destination,
            notes=notes[:500], created_by=actor[:150],
        )
        _event(t, "created", f"{actor} {t.number} transferini yaratdi: {source.name} → {destination.name}", actor)
    return t


def update_draft(transfer_id, actor: str, lines: list[dict], notes: str | None = None, source_id=None, destination_id=None) -> StockTransfer:
    """
    Replaces the draft's product list with `lines` = [{variant_id, quantity, batch?, expiry?}] (absolute quantities --
    re-sending the same list is harmless). Validates products, positive quantities and stock at the source.
    """
    with transaction.atomic():
        t = _locked(transfer_id)
        if t.status != S.DRAFT:
            raise stock.conflict("NOT_EDITABLE", "Only a draft transfer can be edited.")
        if source_id and destination_id and (str(t.source_id) != str(source_id) or str(t.destination_id) != str(destination_id)):
            t.source, t.destination = _stores(source_id, destination_id)
            _event(t, "locations", f"Yo'nalish o'zgardi: {t.source.name} → {t.destination.name}", actor)
        if notes is not None:
            t.notes = notes[:500]
        wanted: dict = {}
        for raw in lines:
            try:
                vid, qty = uuid.UUID(str(raw.get("variant_id"))), int(raw.get("quantity"))
            except (TypeError, ValueError) as exc:
                raise ValidationFailed("Each line needs a product and a whole quantity.") from exc
            if qty <= 0:
                continue
            if qty > stock.MAX_UNITS_PER_LINE:
                raise ValidationFailed("Quantity is too large.")
            batch = str(raw.get("batch") or "").strip()[:48]
            expiry = stock._parse_date(raw.get("expiry"))
            # a batch is (LOT, expiry) -- the same as StockBatch's identity
            entry = wanted.setdefault((vid, batch, expiry), {"quantity": 0, "expiry": expiry})
            entry["quantity"] += qty
        infos = stock.variant_infos({k[0] for k in wanted})
        inactive = [infos[k[0]].name for k in wanted if k[0] in infos and not infos[k[0]].active]
        if len(infos) != len({k[0] for k in wanted}):
            raise ResourceNotFound("One of the products doesn't exist.")
        if inactive:
            raise stock.conflict("PRODUCT_INACTIVE", f"Inactive product: {', '.join(inactive)}", products=inactive)
        available = stock.available_map(t.source, {k[0] for k in wanted})
        needed: dict = {}
        for (vid, _b, _e), e in wanted.items():
            needed[vid] = needed.get(vid, 0) + e["quantity"]
        short = [{"variant_id": str(v), "name": infos[v].name, "requested": q, "available": available.get(v, 0)} for v, q in needed.items() if q > available.get(v, 0)]
        if short:
            raise stock.conflict("INSUFFICIENT_STOCK", "Not enough stock at the source for some products.", shortages=short)
        # a line pinned to a batch the source holds can't ask for more than that batch has (an unknown batch is only a label)
        from apps.stores.infrastructure import transfer_read

        pinned = [k for k in wanted if k[1] or k[2]]
        if pinned:
            held = {
                (vid, b["batch"], b["expiry"]): b["quantity"]
                for vid, rows in transfer_read.batches(t.source, {k[0] for k in pinned}).items() for b in rows
            }
            short = []
            for vid, batch, expiry in pinned:
                have = held.get((vid, batch, expiry.isoformat() if expiry else ""))
                if have is not None and wanted[(vid, batch, expiry)]["quantity"] > have:
                    label = " · ".join(x for x in (batch, expiry.strftime("%d.%m.%Y") if expiry else "") if x)
                    short.append({"variant_id": str(vid), "name": f"{infos[vid].name} ({label})", "requested": wanted[(vid, batch, expiry)]["quantity"], "available": have})
            if short:
                raise stock.conflict("INSUFFICIENT_BATCH_STOCK", "Not enough stock in the chosen batch at the source.", shortages=short)

        from apps.stores.infrastructure.count_service import cost_map

        costs = cost_map({k[0] for k in wanted})  # value the transfer at cost (latest receipt), not at the selling price
        before = {(i.product_variant_id, i.batch_number, i.expiry_date): i.expected_quantity for i in t.items.all()}
        t.items.all().delete()
        for (vid, batch, _exp), e in wanted.items():
            info = infos[vid]
            StockTransferItem.objects.create(
                transfer=t, product_variant_id=vid, name=info.name[:255], sku=info.sku[:64], barcode=info.barcode[:64],
                expected_quantity=e["quantity"], unit_cost=costs.get(vid) or 0, batch_number=batch, expiry_date=e["expiry"],
            )
        after = {k: e["quantity"] for k, e in wanted.items()}
        if before != after:
            changes = [f"{infos[k[0]].name} ×{q}" for k, q in after.items() if before.get(k) != q]
            removed = len(set(before) - set(after))
            _event(t, "items", ("Mahsulotlar yangilandi: " + ", ".join(changes[:6]) + (" …" if len(changes) > 6 else "") + (f"; {removed} ta olib tashlandi" if removed else "")).strip(), actor,
                   {"lines": len(before), "units": sum(before.values())}, {"lines": len(after), "units": sum(after.values())})
        t.save()
    return t


def mark_ready(transfer_id, actor: str) -> StockTransfer:
    """Checks every line against the source's available stock and reserves it (the units stop being sellable)."""
    with transaction.atomic():
        t = _locked(transfer_id)
        items = list(t.items.all())
        if not items or not any(i.expected_quantity for i in items):
            raise stock.conflict("EMPTY_TRANSFER", "Add at least one product.")
        _go(t, S.READY, actor, f"{actor} transferni jo'natishga tayyorladi — mahsulotlar band qilindi")
        for i in items:
            stock.move(t.source, i.product_variant_id, 0, StockMovementType.RESERVATION, reserve=i.expected_quantity, reference=t.number, actor=actor,
                       batch_number=i.batch_number, expiry_date=i.expiry_date, document_id=t.id)
        t.ready_at = timezone.now()
        t.save()
    return t


def back_to_draft(transfer_id, actor: str) -> StockTransfer:
    with transaction.atomic():
        t = _locked(transfer_id)
        _go(t, S.DRAFT, actor, f"{actor} transferni qoralamaga qaytardi — bandlik bekor qilindi")
        _release(t, actor)
        t.save()
    return t


def _release(t: StockTransfer, actor: str) -> None:
    for i in t.items.all():
        if i.expected_quantity:
            stock.move(t.source, i.product_variant_id, 0, StockMovementType.RELEASE, reserve=-i.expected_quantity, reference=t.number, actor=actor, document_id=t.id)


def cancel(transfer_id, actor: str, reason: str = "") -> StockTransfer:
    with transaction.atomic():
        t = _locked(transfer_id)
        was_ready = t.status == S.READY
        _go(t, S.CANCELLED, actor, f"{actor} transferni bekor qildi" + (f": {reason}" if reason else ""))
        if was_ready:
            _release(t, actor)
        t.cancelled_by, t.cancelled_at, t.cancel_reason = actor[:150], timezone.now(), reason[:255]
        t.save()
    return t


# ---------------------------------------------------------------- pick & dispatch


def save_pick(transfer_id, actor: str, picked: dict) -> StockTransfer:
    """Scanned-at-the-source counts {item_id: qty} (absolute). Only while READY."""
    with transaction.atomic():
        t = _locked(transfer_id)
        if t.status != S.READY:
            raise stock.conflict("NOT_READY", "Only a transfer that is ready to send can be picked.")
        items = {str(i.id): i for i in t.items.all()}
        for item_id, qty in (picked or {}).items():
            item = items.get(str(item_id))
            if item is None:
                raise ResourceNotFound("That product is not on this transfer.")
            qty = int(qty)
            if qty < 0 or qty > item.expected_quantity:
                raise stock.conflict("PICK_ABOVE_PLANNED", f"{item.name}: can't pick more than the {item.expected_quantity} planned (reserved).", item_id=str(item.id), planned=item.expected_quantity)
            if qty != item.picked_quantity:
                StockTransferItem.objects.filter(pk=item.pk).update(picked_quantity=qty)
    return t


def dispatch(transfer_id, actor: str, picked: dict | None = None, confirm_mismatch: bool = False) -> StockTransfer:
    """
    Sends the shipment. Picked counts must match the plan, or the mismatch is explicitly confirmed (then only
    the picked units leave). Expired batches can't be sent. The source's reservation is released and the
    picked units leave its stock (TRANSFER_OUT) -- they are now "in transit" on this document.
    """
    today = timezone.localdate()
    with transaction.atomic():
        if picked is not None:
            save_pick(transfer_id, actor, picked)
        t = _locked(transfer_id)
        if t.status != S.READY:
            raise stock.conflict("NOT_READY", "Only a transfer that is ready to send can be dispatched.")
        items = list(t.items.all())
        expired = [i.name for i in items if i.expiry_date and i.expiry_date < today and i.picked_quantity]
        if expired:
            raise stock.conflict("EXPIRED_BATCH", f"Expired batch can't be sent: {', '.join(expired)}", products=expired)
        mismatches = [{"item_id": str(i.id), "name": i.name, "planned": i.expected_quantity, "picked": i.picked_quantity} for i in items if i.picked_quantity != i.expected_quantity]
        if mismatches and not confirm_mismatch:
            raise stock.conflict("PICK_MISMATCH", "Scanned quantities differ from the plan. Confirm to send only what was scanned.", mismatches=mismatches)
        if not sum(i.picked_quantity for i in items):
            raise stock.conflict("EMPTY_TRANSFER", "Nothing was picked -- scan the products before sending.")
        _go(t, S.IN_TRANSIT, actor, f"{actor} transferni jo'natdi ({sum(i.picked_quantity for i in items)} dona)" + (" — rejadan farqi tasdiqlandi" if mismatches else ""))
        for i in items:
            if i.expected_quantity:
                stock.move(t.source, i.product_variant_id, 0, StockMovementType.RELEASE, reserve=-i.expected_quantity, reference=t.number, actor=actor, document_id=t.id)
            allocations = []
            if i.picked_quantity:
                m = stock.move(t.source, i.product_variant_id, -i.picked_quantity, StockMovementType.TRANSFER_OUT, reference=t.number, actor=actor,
                               note=f"→ {t.destination.name}", batch_number=i.batch_number, expiry_date=i.expiry_date, document_id=t.id)
                allocations = m.allocations  # the batches travel with the units
            StockTransferItem.objects.filter(pk=i.pk).update(dispatched_quantity=i.picked_quantity, batch_allocations=allocations)
        if mismatches:
            _event(t, "pick_mismatch", "Jo'natishdagi farq: " + "; ".join(f"{m['name']}: reja {m['planned']}, jo'natildi {m['picked']}" for m in mismatches)[:280], actor, {"mismatches": mismatches})
        t.dispatched_by, t.dispatched_at = actor[:150], timezone.now()
        t.save()
    return t


# ---------------------------------------------------------------- receiving


def _slice(allocations: list, start: int, units: int) -> list:
    """Units [start, start+units) of a dispatched line, as batches -- receipts post the batches in the order they left."""
    out, pos = [], 0
    for a in allocations or []:
        lo, hi = pos, pos + int(a.get("qty") or 0)
        pos = hi
        take = min(hi, start + units) - max(lo, start)
        if take > 0:
            out.append({"batch": a.get("batch") or "", "expiry": a.get("expiry"), "qty": take})
    return out


def _apply_counts(t: StockTransfer, counts: dict, reasons: dict | None) -> list[StockTransferItem]:
    items = {str(i.id): i for i in t.items.all()}
    for item_id, qty in (counts or {}).items():
        item = items.get(str(item_id))
        if item is None:
            raise ResourceNotFound("That product is not on this transfer.")
        qty = int(qty)
        if qty < item.received_posted:
            raise stock.conflict("BELOW_POSTED", f"{item.name}: {item.received_posted} units are already accepted into stock.", item_id=str(item.id), posted=item.received_posted)
        if qty > max(item.dispatched_quantity * 3, item.dispatched_quantity + 50):
            raise stock.conflict("COUNT_UNREALISTIC", f"{item.name}: {qty} is far above the {item.dispatched_quantity} sent -- check the count.", item_id=str(item.id))
        item.received_quantity = qty
    for item_id, r in (reasons or {}).items():
        item = items.get(str(item_id))
        if item is None:
            continue
        code = (r or {}).get("reason") or ""
        if code and code not in DiscrepancyReason.values:
            raise ValidationFailed("Unknown discrepancy reason.")
        item.discrepancy_reason = code
        item.discrepancy_note = str((r or {}).get("note") or "")[:255]
    for item in items.values():
        item.save(update_fields=["received_quantity", "discrepancy_reason", "discrepancy_note"])
    return list(items.values())


def save_receiving(transfer_id, actor: str, counts: dict, reasons: dict | None = None) -> StockTransfer:
    """Counts scanned at the destination so far (absolute per item). Nothing enters stock yet."""
    with transaction.atomic():
        t = _locked(transfer_id)
        if t.status not in RECEIVABLE or t.discrepancy_open:
            raise stock.conflict("NOT_RECEIVABLE", "This transfer is not being received.")
        first = t.status == S.IN_TRANSIT
        _apply_counts(t, counts, reasons)
        if first:
            _go(t, S.RECEIVING, actor, f"{actor} qabul qilishni boshladi")
            t.save()
    return t


def confirm_receipt(transfer_id, actor: str, counts: dict | None = None, reasons: dict | None = None, final: bool = True) -> StockTransfer:
    """
    Posts the counted units into the destination's stock (only what wasn't posted before).
    final=False: a partial receipt -- more boxes may still come, the transfer stays PARTIALLY_RECEIVED.
    final=True:  the receipt is closed; any shortage / excess must carry a reason and waits for a manager's approval.
    """
    with transaction.atomic():
        t = _locked(transfer_id)
        if t.status not in RECEIVABLE or t.discrepancy_open:
            raise stock.conflict("NOT_RECEIVABLE", "This transfer is not being received.")
        items = _apply_counts(t, counts or {}, reasons)
        if final:
            missing = [i.name for i in items if i.received_quantity != i.dispatched_quantity and not i.discrepancy_reason]
            if missing:
                raise stock.conflict("DISCREPANCY_REASON_REQUIRED", "Give a reason for every shortage / excess.", products=missing)
        posted_now = 0
        for i in items:
            delta = i.received_quantity - i.received_posted
            if delta > 0:
                stock.move(t.destination, i.product_variant_id, delta, StockMovementType.TRANSFER_IN, reference=t.number, actor=actor,
                           note=f"← {t.source.name}", batch_number=i.batch_number, expiry_date=i.expiry_date, document_id=t.id,
                           placement=_slice(i.batch_allocations, i.received_posted, delta))
                StockTransferItem.objects.filter(pk=i.pk).update(received_posted=i.received_quantity)
                posted_now += delta
        received = sum(i.received_quantity for i in items)
        sent = sum(i.dispatched_quantity for i in items)
        diffs = [i for i in items if i.received_quantity != i.dispatched_quantity]
        if not final:
            _go(t, S.PARTIALLY_RECEIVED, actor, f"{actor} qisman qabul qildi: +{posted_now} dona omborga kirdi (jami {received}/{sent})")
        elif diffs:
            t.discrepancy_open = True
            _go(t, S.PARTIALLY_RECEIVED, actor, f"{actor} qabulni yakunladi: {received}/{sent} dona — tafovut tasdiqlanishi kerak")
            for i in diffs:
                d = i.received_quantity - i.dispatched_quantity
                _event(t, "discrepancy", f"{i.name}: {'kamomad' if d < 0 else 'ortiqcha'} {abs(d)} dona — {DiscrepancyReason(i.discrepancy_reason).label}" + (f" ({i.discrepancy_note})" if i.discrepancy_note else ""), actor,
                       {"dispatched": i.dispatched_quantity}, {"received": i.received_quantity, "reason": i.discrepancy_reason})
        else:
            _go(t, S.RECEIVED, actor, f"{actor} hammasini qabul qildi: {received}/{sent} dona — farq yo'q")
        if final:
            t.received_by, t.received_at = actor[:150], timezone.now()
        t.save()
    return t


def approve_discrepancies(transfer_id, actor: str, resolutions: dict) -> StockTransfer:
    """
    A manager decides every shortage / excess: {item_id: resolution}.
      shortage → "write_off" (lost in transit: recorded, no stock change) | "return_to_source" (never left: back on the source's stock)
      excess   → "deduct_source" (sent unrecorded: taken off the source's stock) | "accept" (found extra: kept)
    """
    with transaction.atomic():
        t = _locked(transfer_id)
        if not t.discrepancy_open:
            raise stock.conflict("NO_DISCREPANCY", "There is no discrepancy to approve.")
        now = timezone.now()
        for i in t.items.all():
            d = i.received_quantity - i.dispatched_quantity
            if d == 0:
                continue
            choice = (resolutions or {}).get(str(i.id))
            allowed = SHORTAGE_RESOLUTIONS if d < 0 else EXCESS_RESOLUTIONS
            if choice not in allowed:
                raise stock.conflict("RESOLUTION_REQUIRED", f"{i.name}: choose how to settle the {'shortage' if d < 0 else 'excess'}.", item_id=str(i.id), allowed=list(allowed))
            if choice == "return_to_source":
                stock.move(t.source, i.product_variant_id, -d, StockMovementType.ADJUSTMENT, reference=t.number, actor=actor,
                           note=f"Transfer kamomadi manbaga qaytarildi: {i.discrepancy_note or i.get_discrepancy_reason_display()}", document_id=t.id,
                           placement=_slice(i.batch_allocations, i.received_quantity, -d))
            elif choice == "deduct_source":
                stock.move(t.source, i.product_variant_id, -d, StockMovementType.ADJUSTMENT, reference=t.number, actor=actor,
                           note="Transfer ortiqchasi manbadan ayirildi", document_id=t.id)
            label = {"write_off": "hisobdan chiqarildi", "return_to_source": "manbaga qaytarildi", "deduct_source": "manbadan ayirildi", "accept": "qabul qilindi"}[choice]
            StockTransferItem.objects.filter(pk=i.pk).update(resolution=choice, resolved_by=actor[:150], resolved_at=now)
            _event(t, "resolved", f"{i.name}: {'kamomad' if d < 0 else 'ortiqcha'} {abs(d)} dona — {label}", actor, {"difference": d}, {"resolution": choice})
        t.discrepancy_open = False
        _go(t, S.RECEIVED, actor, f"{actor} tafovutni tasdiqladi")
        t.save()
    return t


def complete(transfer_id, actor: str) -> StockTransfer:
    with transaction.atomic():
        t = _locked(transfer_id)
        _go(t, S.COMPLETED, actor, f"{actor} transferni yakunladi")
        t.completed_by, t.completed_at = actor[:150], timezone.now()
        t.save()
    return t


# ---------------------------------------------------------------- read models


def summary(t: StockTransfer) -> dict:
    items = list(t.items.all())
    return {
        "lines": len(items),
        "planned": sum(i.expected_quantity for i in items),
        "picked": sum(i.picked_quantity for i in items),
        "dispatched": sum(i.dispatched_quantity for i in items),
        "received": sum(i.received_quantity for i in items),
        "posted": sum(i.received_posted for i in items),
        "shortage": sum(max(0, i.dispatched_quantity - i.received_quantity) for i in items),
        "excess": sum(max(0, i.received_quantity - i.dispatched_quantity) for i in items),
        "value": sum((i.unit_cost * (i.dispatched_quantity or i.expected_quantity) for i in items), 0),
    }


def locations(kind: str | None = None):
    qs = Store.objects.exclude(status="inactive").order_by("-kind", "name")  # warehouses first ("warehouse" > "store")
    if kind:
        qs = qs.filter(kind=kind)
    return qs


def is_warehouse(store: Store) -> bool:
    return store.kind == StoreKind.WAREHOUSE


def today() -> date:
    return timezone.localdate()
