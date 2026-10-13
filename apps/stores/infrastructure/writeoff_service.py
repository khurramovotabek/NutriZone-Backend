"""
Write-offs (Hisobdan chiqarish) -- damaged, expired, defective, lost or tester goods leave a location's stock
with a reason and a manager's approval, outside of a stock count.

    create ──▶ PENDING ──approve──▶ APPROVED     (units deducted: DAMAGE / EXPIRED / WRITE_OFF ledger rows)
                  │──reject───▶ REJECTED         (reservation released, stock unchanged)
                  └──cancel───▶ CANCELLED        (by the author, same as reject)

* create   the units are reserved at once (RESERVATION, reference HC-…): goods set aside as broken
           can't be sold or sent while they wait for approval. Fails if the location doesn't have them available.
* approve  per line: reservation released and the units deducted, in one transaction. Someone with the
           approve permission can create and approve in one step.
Value is at cost (count_service.cost_map) and frozen on the document.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.stores.infrastructure import stock_service as stock
from apps.stores.infrastructure.models import (
    StockMovementType,
    Store,
    WriteOff,
    WriteOffItem,
    WriteOffReason,
    WriteOffStatus,
)
from common.exceptions import ResourceNotFound, ValidationFailed

S = WriteOffStatus
MOVEMENT = {
    WriteOffReason.DAMAGED: StockMovementType.DAMAGE, WriteOffReason.DEFECT: StockMovementType.DAMAGE,
    WriteOffReason.EXPIRED: StockMovementType.EXPIRED,
}


def _locked(write_off_id) -> WriteOff:
    w = WriteOff.objects.select_for_update().select_related("store").filter(id=write_off_id).first()
    if w is None:
        raise ResourceNotFound("Write-off not found.")
    return w


def _pending(w: WriteOff) -> None:
    if w.status != S.PENDING:
        raise stock.conflict("INVALID_STATE", f"This write-off is already '{w.get_status_display()}'.", status=w.status)


def _per_variant(items) -> dict:
    units: dict = {}
    for i in items:
        units[i.product_variant_id] = units.get(i.product_variant_id, 0) + i.quantity
    return units


def create(store_id, actor: str, lines: list[dict], note: str = "") -> WriteOff:
    """lines = [{variant_id, quantity, reason, batch?, expiry?, note?}] -- same product + reason + batch lines are merged."""
    from apps.stores.infrastructure.count_service import cost_map

    try:
        store = Store.objects.get(id=uuid.UUID(str(store_id)))
    except (ValueError, TypeError, Store.DoesNotExist) as exc:
        raise ResourceNotFound("Choose a location.") from exc
    merged: dict = {}
    for raw in lines or []:
        try:
            vid, qty = uuid.UUID(str(raw.get("variant_id"))), int(raw.get("quantity"))
        except (TypeError, ValueError) as exc:
            raise ValidationFailed("Each line needs a product and a whole quantity.") from exc
        if qty <= 0:
            continue
        if qty > stock.MAX_UNITS_PER_LINE:
            raise ValidationFailed("Quantity is too large.")
        reason = raw.get("reason") or ""
        if reason not in WriteOffReason.values:
            raise ValidationFailed("Choose a reason for every product.")
        batch = str(raw.get("batch") or "").strip()[:48]
        line = merged.setdefault((vid, reason, batch), {"quantity": 0, "expiry": stock._parse_date(raw.get("expiry")), "note": str(raw.get("note") or "")[:255]})
        line["quantity"] += qty
    if not merged:
        raise stock.conflict("EMPTY_WRITE_OFF", "Add at least one product.")
    infos = stock.variant_infos({k[0] for k in merged})
    if len(infos) != len({k[0] for k in merged}):
        raise ResourceNotFound("One of the products doesn't exist.")
    costs = cost_map({k[0] for k in merged})
    with transaction.atomic():
        w = WriteOff.objects.create(number=stock.next_number("HC", "stores_writeoff_number_seq"), store=store, note=(note or "")[:255], created_by=actor[:150])
        items = []
        for (vid, reason, batch), line in merged.items():
            info = infos[vid]
            items.append(WriteOffItem.objects.create(
                write_off=w, product_variant_id=vid, name=info.name[:255], sku=info.sku[:64], barcode=(info.barcode or "")[:64], quantity=line["quantity"],
                reason=reason, batch_number=batch, expiry_date=line["expiry"], unit_cost=costs.get(vid) or 0, note=line["note"],
            ))
        available = stock.available_map(store, {i.product_variant_id for i in items})
        need = _per_variant(items)
        short = [{"name": infos[v].name, "requested": q, "available": available.get(v, 0)} for v, q in need.items() if q > available.get(v, 0)]
        if short:
            raise stock.conflict("INSUFFICIENT_STOCK", "The location doesn't have that many available: " + ", ".join(f"{s['name']} ({s['available']})" for s in short), shortages=short)
        for vid, q in need.items():
            stock.move(store, vid, 0, StockMovementType.RESERVATION, reserve=q, reference=w.number, actor=actor, note="Hisobdan chiqarish: tasdiq kutilmoqda", document_id=w.id)
        w.total_units = sum(i.quantity for i in items)
        w.total_value = sum((i.unit_cost * i.quantity for i in items), Decimal(0))
        w.save(update_fields=["total_units", "total_value"])
    return w


def approve(write_off_id, actor: str, note: str = "") -> WriteOff:
    with transaction.atomic():
        w = _locked(write_off_id)
        _pending(w)
        items = list(w.items.all())
        for vid, q in _per_variant(items).items():
            stock.move(w.store, vid, 0, StockMovementType.RELEASE, reserve=-q, reference=w.number, actor=actor, document_id=w.id)
        for i in items:
            label = WriteOffReason(i.reason).label
            stock.move(w.store, i.product_variant_id, -i.quantity, MOVEMENT.get(i.reason, StockMovementType.WRITE_OFF), reference=w.number, actor=actor,
                       note=f"Hisobdan chiqarish: {label}" + (f" — {i.note}" if i.note else ""), batch_number=i.batch_number, expiry_date=i.expiry_date, document_id=w.id)
        w.status, w.decided_by, w.decided_at, w.decision_note = S.APPROVED, actor[:150], timezone.now(), (note or "")[:255]
        w.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
    return w


def _close(write_off_id, actor: str, status: str, note: str) -> WriteOff:
    with transaction.atomic():
        w = _locked(write_off_id)
        _pending(w)
        for vid, q in _per_variant(w.items.all()).items():
            stock.move(w.store, vid, 0, StockMovementType.RELEASE, reserve=-q, reference=w.number, actor=actor, document_id=w.id)
        w.status, w.decided_by, w.decided_at, w.decision_note = status, actor[:150], timezone.now(), (note or "")[:255]
        w.save(update_fields=["status", "decided_by", "decided_at", "decision_note"])
    return w


def reject(write_off_id, actor: str, note: str = "") -> WriteOff:
    if not (note or "").strip():
        raise ValidationFailed("Write why the write-off is rejected.")
    return _close(write_off_id, actor, S.REJECTED, note)


def cancel(write_off_id, actor: str, note: str = "") -> WriteOff:
    return _close(write_off_id, actor, S.CANCELLED, note)
