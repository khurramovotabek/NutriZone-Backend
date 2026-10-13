"""
Read model of an inventory transfer -- one shape for every screen that shows it: the Dashboard workspace
(warehouse_admin), the branch's "Mahsulot qabul qilish" page (my-store API) and the Excel / printed waybill.

Nothing here changes stock or the document; all writes stay in transfer_service.

Batches: a line is a product + the batch the sender chose ("" = no batch chosen, FEFO at dispatch). What really left
the source is `batch_allocations` (filled at dispatch), and the destination posts received units into those batches in
the same order (transfer_service._slice). `batch_rows()` splits every line that way, so the waybill shows one row per
batch with sent / received quantities exactly as the stock ledger has them.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.stores.infrastructure import stock_service, transfer_service
from apps.stores.infrastructure.models import StockBatch, StockTransfer, Store

TZ = ZoneInfo("Asia/Tashkent")
RESOLUTION_LABELS = {"write_off": "hisobdan chiqarildi", "return_to_source": "manbaga qaytarildi", "deduct_source": "manbadan ayirildi", "accept": "qabul qilindi"}


def local(dt, fmt: str = "%d.%m.%Y %H:%M") -> str | None:
    return timezone.localtime(dt, TZ).strftime(fmt) if dt else None


def location(s: Store) -> dict:
    return {"id": str(s.id), "name": s.name, "kind": s.kind, "color": s.color or "#94a3b8", "city": s.city, "address": s.address}


def batches(store: Store, variant_ids) -> dict:
    """{variant_id: [{batch, expiry, quantity, expired}]} -- a location's batches with stock, in the order a sale or transfer takes them (FEFO)."""
    today = timezone.localdate()
    out: dict = {}
    rows = StockBatch.objects.filter(store=store, product_variant_id__in=list(variant_ids), quantity__gt=0)
    for b in sorted(rows, key=lambda b: (b.expiry_date is None, b.expiry_date or date.max, b.received_at)):
        out.setdefault(b.product_variant_id, []).append({
            "batch": b.batch_number, "expiry": b.expiry_date.isoformat() if b.expiry_date else "", "quantity": b.quantity,
            "expired": bool(b.expiry_date and b.expiry_date < today),
        })
    return out


def _allocations(item) -> list[dict]:
    """What left the source per batch; before dispatch the planned batch (or none)."""
    allocs = [a for a in (item.batch_allocations or []) if int(a.get("qty") or 0) > 0]
    if allocs:
        return [{"batch": a.get("batch") or "", "expiry": a.get("expiry") or "", "qty": int(a["qty"])} for a in allocs]
    return [{"batch": item.batch_number, "expiry": item.expiry_date.isoformat() if item.expiry_date else "", "qty": item.dispatched_quantity or item.expected_quantity}]


def batch_rows(t: StockTransfer, items=None) -> list[dict]:
    """One row per (line × batch that left the source): sent, received (as posted into that batch), difference."""
    items = list(items if items is not None else t.items.all())
    received_known = t.status not in ("draft", "ready", "in_transit", "cancelled")
    out = []
    for i in items:
        allocs = _allocations(i)
        start = 0
        for k, a in enumerate(allocs):
            sent = a["qty"]
            got = None
            if received_known:
                # received units fill the batches in the order they left (transfer_service._slice); an excess lands on the last row
                left = max(0, i.received_quantity - start)
                got = left if k == len(allocs) - 1 else min(sent, left)
            start += sent
            out.append({
                "item": i, "item_id": str(i.id), "name": i.name, "sku": i.sku, "barcode": i.barcode, "batch": a["batch"], "expiry": a["expiry"],
                "sent": sent, "received": got, "difference": (got - sent) if got is not None else None,
                "unit_cost": i.unit_cost, "value": i.unit_cost * sent, "split": len(allocs) > 1,
            })
    return out


def payload(t: StockTransfer, *, events: bool = True) -> dict:
    """The transfer as every screen needs it (amounts as strings, times in Tashkent)."""
    items = list(t.items.all())
    variant_ids = [i.product_variant_id for i in items]
    infos = stock_service.variant_infos(variant_ids)
    src = stock_service.available_map(t.source, variant_ids)
    dst = stock_service.available_map(t.destination, variant_ids)
    from apps.stores.infrastructure.count_service import cost_info

    sources = {vid: src for vid, (_cost, src) in cost_info(variant_ids).items()}
    summary = transfer_service.summary(t)
    summary["batches"] = len({(i.product_variant_id, a["batch"], a["expiry"]) for i in items for a in _allocations(i)})
    summary["products"] = len(set(variant_ids))
    summary["differences"] = sum(1 for i in items if i.dispatched_quantity and i.received_quantity != i.dispatched_quantity)
    return {
        "id": str(t.pk), "number": t.number, "status": t.status, "status_label": t.get_status_display(), "discrepancy_open": t.discrepancy_open,
        "source": location(t.source), "destination": location(t.destination), "notes": t.notes,
        "created_by": t.created_by, "created_at": local(t.created_at), "ready_at": local(t.ready_at),
        "dispatched_by": t.dispatched_by, "dispatched_at": local(t.dispatched_at),
        "received_by": t.received_by, "received_at": local(t.received_at), "completed_at": local(t.completed_at), "completed_by": t.completed_by,
        "cancelled_at": local(t.cancelled_at), "cancel_reason": t.cancel_reason, "updated_at": t.updated_at.isoformat(),
        "summary": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in summary.items()},
        "items": [{
            "id": str(i.id), "variant_id": str(i.product_variant_id), "name": i.name, "sku": i.sku, "barcode": i.barcode,
            "size": infos[i.product_variant_id].size if i.product_variant_id in infos else None,
            "image_url": infos[i.product_variant_id].image_url if i.product_variant_id in infos else None,
            "planned": i.expected_quantity, "picked": i.picked_quantity, "dispatched": i.dispatched_quantity, "received": i.received_quantity,
            "posted": i.received_posted, "unit_cost": str(i.unit_cost), "cost_source": sources.get(i.product_variant_id) or "", "batch": i.batch_number, "expiry": i.expiry_date.isoformat() if i.expiry_date else "",
            "allocations": _allocations(i) if i.batch_allocations else [],
            "reason": i.discrepancy_reason, "note": i.discrepancy_note, "resolution": i.resolution, "resolution_label": RESOLUTION_LABELS.get(i.resolution, ""),
            "resolved_by": i.resolved_by, "source_available": src.get(i.product_variant_id, 0), "destination_available": dst.get(i.product_variant_id, 0),
        } for i in items],
        "events": [{"at": local(e.created_at), "actor": e.actor, "action": e.action, "message": e.message} for e in t.events.order_by("-created_at")] if events else [],
    }


def lookup(code: str, location_store: Store | None = None) -> dict | None:
    """A scanned barcode / typed SKU -> the product, its stock and batches at `location_store`, and the batch the code itself names (an extra batch barcode)."""
    from apps.stores.infrastructure.models import StoreProductStock

    match = stock_service.find_match(code)
    if match is None:
        return None
    variant = match.variant
    info = stock_service.variant_infos([variant.id])[variant.id]
    row = StoreProductStock.objects.filter(store=location_store, product_variant=variant).first() if location_store else None
    return {
        "variant_id": str(variant.id), "name": info.name, "sku": info.sku, "barcode": info.barcode, "size": info.size, "image_url": info.image_url,
        "price": str(info.price) if info.price is not None else None, "active": info.active,
        "available": row.available if row else 0, "quantity": row.quantity if row else 0, "reserved": row.reserved_quantity if row else 0,
        "matched": match.barcode, "is_extra_barcode": match.is_extra, "batch": match.batch,
        "expiry": match.expires_at.isoformat() if match.expires_at else None,
        "batches": batches(location_store, [variant.id]).get(variant.id, []) if location_store else [],
    }
