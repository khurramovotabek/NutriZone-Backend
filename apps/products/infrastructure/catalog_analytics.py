"""
Catalog analytics for the Dashboard lists (Mahsulotlar, Variantlar, Brendlar, Kategoriyalar, Ta'mlar).

One snapshot, cached for a minute, feeds every list:
- sales per variant over the last N days -- POS completed sales (minus refunded units) + online orders that
  actually earned money (delivered/completed, the same rule as the dashboard's online revenue chart);
- stock per variant from `StoreProductStock` (the WMS source of truth: branches + warehouses, on hand/reserved);
- the same numbers rolled up per product, brand, category and flavour.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.utils import timezone

EARNED_ORDER_STATUSES = ("delivered", "completed")
CACHE_SECONDS = 60


@dataclass
class Numbers:
    units: int = 0
    revenue: Decimal = Decimal("0")
    prev_units: int = 0
    prev_revenue: Decimal = Decimal("0")

    def add(self, other: "Numbers") -> None:
        self.units += other.units
        self.revenue += other.revenue
        self.prev_units += other.prev_units
        self.prev_revenue += other.prev_revenue

    @property
    def change_pct(self) -> int | None:
        if not self.prev_revenue:
            return None
        return round(float((self.revenue - self.prev_revenue) / self.prev_revenue * 100))


@dataclass
class Snapshot:
    days: int
    variant_sales: dict = field(default_factory=dict)      # variant_id -> Numbers
    variant_stock: dict = field(default_factory=dict)      # variant_id -> (on_hand, reserved)
    variant_product: dict = field(default_factory=dict)    # variant_id -> product_id
    product_sales: dict = field(default_factory=dict)      # product_id -> Numbers
    product_stock: dict = field(default_factory=dict)      # product_id -> on_hand
    brand_sales: dict = field(default_factory=dict)
    category_sales: dict = field(default_factory=dict)
    flavour_sales: dict = field(default_factory=dict)
    total: Numbers = field(default_factory=Numbers)


def _sales(start, end) -> dict:
    """variant_id (or ('product', product_id) for POS lines without a variant) -> [units, revenue]."""
    from django.db.models import F, Sum

    from apps.ordering.infrastructure.models import OrderLineItemModel
    from apps.pos.infrastructure.models import SaleLineItemModel

    out: dict = defaultdict(lambda: [0, Decimal("0")])
    pos = (
        SaleLineItemModel.objects.filter(sale__status__in=("completed", "refunded"), sale__completed_at__gte=start, sale__completed_at__lt=end)
        .values("product_variant_id", "product_id")
        .annotate(units=Sum(F("quantity") - F("refunded_quantity")), revenue=Sum((F("quantity") - F("refunded_quantity")) * F("unit_price_amount")))
    )
    for row in pos:
        key = row["product_variant_id"] or ("product", row["product_id"])
        out[key][0] += int(row["units"] or 0)
        out[key][1] += row["revenue"] or Decimal("0")
    online = (
        OrderLineItemModel.objects.filter(order__status__in=EARNED_ORDER_STATUSES, order__placed_at__gte=start, order__placed_at__lt=end)
        .exclude(status="cancelled")
        .values("product_variant_id")
        .annotate(units=Sum("quantity"), revenue=Sum(F("quantity") * F("unit_price_amount") - F("discount_amount")))
    )
    for row in online:
        out[row["product_variant_id"]][0] += int(row["units"] or 0)
        out[row["product_variant_id"]][1] += row["revenue"] or Decimal("0")
    return out


def build(days: int = 30) -> Snapshot:
    from django.db.models import Sum

    from apps.products.infrastructure import models as orm
    from apps.stores.infrastructure.models import StoreProductStock

    now = timezone.now()
    cur, prev = _sales(now - timedelta(days=days), now), _sales(now - timedelta(days=days * 2), now - timedelta(days=days))
    snap = Snapshot(days=days)

    variants = list(orm.ProductVariant.objects.values_list("id", "product_id"))
    snap.variant_product = dict(variants)
    products = {p["id"]: p for p in orm.Product.objects.values("id", "brand_id", "category_id")}
    flavours_of: dict = defaultdict(list)
    for pid, fid in orm.ProductFlavour.objects.values_list("product_id", "flavour_id"):
        flavours_of[pid].append(fid)

    def numbers_for(key) -> Numbers:
        c, p = cur.get(key, (0, Decimal("0"))), prev.get(key, (0, Decimal("0")))
        return Numbers(units=c[0], revenue=c[1], prev_units=p[0], prev_revenue=p[1])

    keys = set(cur) | set(prev)
    for key in keys:
        n = numbers_for(key)
        if isinstance(key, tuple):
            product_id = key[1]
        else:
            snap.variant_sales[key] = n
            product_id = snap.variant_product.get(key)
        snap.total.add(n)
        if product_id is None:
            continue
        snap.product_sales.setdefault(product_id, Numbers()).add(n)
        p = products.get(product_id)
        if p is None:
            continue
        if p["brand_id"]:
            snap.brand_sales.setdefault(p["brand_id"], Numbers()).add(n)
        if p["category_id"]:
            snap.category_sales.setdefault(p["category_id"], Numbers()).add(n)
        for fid in flavours_of.get(product_id, ()):
            snap.flavour_sales.setdefault(fid, Numbers()).add(n)

    for row in StoreProductStock.objects.values("product_variant_id").annotate(q=Sum("quantity"), r=Sum("reserved_quantity")):
        vid = row["product_variant_id"]
        snap.variant_stock[vid] = (int(row["q"] or 0), int(row["r"] or 0))
        pid = snap.variant_product.get(vid)
        if pid:
            snap.product_stock[pid] = snap.product_stock.get(pid, 0) + int(row["q"] or 0)
    return snap


def snapshot(days: int = 30) -> Snapshot:
    key = f"nz:catalog-analytics:{days}"
    try:
        cached = cache.get(key)
    except Exception:  # noqa: BLE001
        cached = None
    if cached is not None:
        return cached
    snap = build(days)
    try:
        cache.set(key, snap, CACHE_SECONDS)
    except Exception:  # noqa: BLE001
        pass
    return snap


# ------------------------------------------------------------------ presentation helpers (shared by the admins)


def money(value) -> str:
    try:
        n = int(Decimal(value or 0))
    except Exception:  # noqa: BLE001
        return "—"
    return f"{n:,}".replace(",", " ")


def compact(value) -> str:
    n = float(value or 0)
    if abs(n) >= 1e9:
        return f"{n / 1e9:.1f}".rstrip("0").rstrip(".") + " mlrd"
    if abs(n) >= 1e6:
        return f"{n / 1e6:.1f}".rstrip("0").rstrip(".") + " mln"
    if abs(n) >= 1e3:
        return f"{round(n / 1e3)} ming"
    return str(int(n))


def ranking(rows: list[tuple[str, Numbers, str]], limit: int = 5) -> list[dict]:
    """[(label, numbers, colour)] -> the top N by revenue, with bar widths relative to the leader."""
    rows = [r for r in rows if r[1].revenue > 0 or r[1].units > 0]
    rows.sort(key=lambda r: (r[1].revenue, r[1].units), reverse=True)
    top = rows[:limit]
    lead = top[0][1].revenue if top and top[0][1].revenue else Decimal("1")
    return [
        {"label": label, "revenue": compact(n.revenue), "units": n.units, "pct": max(int(n.revenue * 100 / lead), 3) if lead else 0, "color": color, "change": n.change_pct}
        for label, n, color in top
    ]


PALETTE = ["#10b981", "#3b82f6", "#8b5cf6", "#f59e0b", "#ec4899", "#14b8a6", "#6366f1", "#f97316", "#0ea5e9", "#84cc16"]


def donut(parts: list[tuple[str, int]], limit: int = 6) -> dict:
    """[(label, value)] -> a CSS conic-gradient donut + its legend (no chart library needed)."""
    parts = sorted([p for p in parts if p[1] > 0], key=lambda p: p[1], reverse=True)
    if len(parts) > limit:
        rest = sum(v for _, v in parts[limit - 1:])
        parts = parts[: limit - 1] + [("Boshqalar", rest)]
    total = sum(v for _, v in parts) or 1
    stops, legend, acc = [], [], 0.0
    for i, (label, value) in enumerate(parts):
        color = PALETTE[i % len(PALETTE)]
        start, acc = acc, acc + value * 100 / total
        stops.append(f"{color} {start:.2f}% {acc:.2f}%")
        legend.append({"label": label, "value": value, "pct": round(value * 100 / total), "color": color})
    return {"gradient": f"conic-gradient({', '.join(stops)})" if stops else "", "legend": legend, "total": sum(v for _, v in parts)}


def change_badge(pct: int | None) -> dict | None:
    if pct is None:
        return None
    return {"text": f"{'+' if pct >= 0 else ''}{pct}%", "up": pct >= 0}
