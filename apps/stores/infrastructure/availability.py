"""
Storefront availability straight from the WMS truth: `StoreProductStock` (on hand − reserved) at active locations.

The storefront used to read the old `inventory.WarehouseInventoryModel` mirror, which drifted from the real shelf
(a branch showed 64 units it no longer had). Every public reader -- product cards, the product page's per-variant
stock and "where to buy" list, catalogue filters, smart search -- now goes through these two functions, so what a
customer sees is exactly what the warehouse and the POS see.

  * sellable(): units that can still be sold online per variant -- every active location (warehouses + branches),
    reserved units excluded. A variant with no stock row anywhere is "not tracked" (absent from the dict).
  * branches(): the active branches (never a warehouse) holding each variant, for "where can I buy it today".
"""
from __future__ import annotations

from apps.stores.infrastructure.models import StoreKind, StoreProductStock, StoreStatus


def _rows(variant_ids):
    ids = list({v for v in variant_ids if v})
    if not ids:
        return []
    return StoreProductStock.objects.filter(product_variant_id__in=ids, store__status=StoreStatus.ACTIVE)


def sellable(variant_ids) -> dict:
    """{variant_id: available units across active locations}; only variants with a stock row are present."""
    out: dict = {}
    if not variant_ids:
        return out
    for vid, qty, res in _rows(variant_ids).values_list("product_variant_id", "quantity", "reserved_quantity"):
        out[vid] = out.get(vid, 0) + max(qty - res, 0)
    return out


def branches(variant_ids) -> dict:
    """{variant_id: [branch row, ...]} -- stocked branches first (most units first), then branches that ran out."""
    if not variant_ids:
        return {}
    rows = _rows(variant_ids).filter(store__kind=StoreKind.STORE).values(
        "product_variant_id", "quantity", "reserved_quantity", "store_id", "store__name", "store__slug", "store__address", "store__city", "store__district",
    )
    out: dict = {}
    for r in rows:
        out.setdefault(r["product_variant_id"], []).append({
            "store_id": str(r["store_id"]), "name": r["store__name"], "slug": r["store__slug"], "address": r["store__address"],
            "city": r["store__city"], "district": r["store__district"], "available_quantity": max(r["quantity"] - r["reserved_quantity"], 0),
        })
    for entries in out.values():
        entries.sort(key=lambda e: (e["available_quantity"] <= 0, -e["available_quantity"], e["name"]))
    return out
