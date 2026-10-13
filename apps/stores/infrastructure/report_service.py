"""
Warehouse reports (Ombor hisobotlari) -- read-only figures from the stock ledger, for one location or all.

* turnover      cost of goods sold in the period (sales − returns, at cost) ÷ stock value now, annualised;
                days of inventory = stock value ÷ COGS per day (how long today's stock lasts at this pace)
* per product   on hand, sold, sales per day, days of cover, last sale, value -- and the ABC class by sales
                value (A = the products making the first 80 % of it, B = the next 15 %, C = the rest)
* dead stock    on hand but not sold in the period
* flow          units in / out by movement type (transfers between locations are left out of "all locations")
Valuation is at cost (count_service.cost_map).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db.models import Max, Q, Sum
from django.utils import timezone

from apps.stores.infrastructure import stock_service as stock
from apps.stores.infrastructure.models import StockMovement, StockMovementType, StoreProductStock

T = StockMovementType
FLOW_IN = (T.RECEIPT, T.TRANSFER_IN, T.RETURN, T.ADJUSTMENT)
FLOW_OUT = (T.SALE, T.TRANSFER_OUT, T.DAMAGE, T.EXPIRED, T.WRITE_OFF, T.ADJUSTMENT)
LOSS = (T.DAMAGE, T.EXPIRED, T.WRITE_OFF)


@dataclass
class Row:
    variant_id: object
    info: object
    on_hand: int
    sold: int
    last_sale: object
    cost: Decimal
    days: int
    abc: str = "C"

    @property
    def value(self) -> Decimal:
        return self.cost * self.on_hand

    @property
    def sales_value(self) -> Decimal:
        return self.cost * self.sold

    @property
    def per_day(self) -> float:
        return self.sold / self.days if self.days else 0

    @property
    def cover(self) -> int | None:
        return int(self.on_hand / self.per_day) if self.per_day else None

    @property
    def dead(self) -> bool:
        return self.on_hand > 0 and self.sold == 0


def build(store_ids=None, days: int = 30) -> dict:
    from apps.stores.infrastructure.count_service import cost_map

    since = timezone.now() - timedelta(days=days)
    moves = StockMovement.objects.filter(created_at__gte=since)
    stocks = StoreProductStock.objects.filter(quantity__gt=0)
    if store_ids is not None:
        moves = moves.filter(store_id__in=list(store_ids))
        stocks = stocks.filter(store_id__in=list(store_ids))
    on_hand: dict = {}
    for r in stocks.values("product_variant_id").annotate(q=Sum("quantity")):
        on_hand[r["product_variant_id"]] = r["q"]
    sold: dict = {}
    for r in moves.filter(movement_type__in=(T.SALE, T.RETURN)).values("product_variant_id").annotate(q=Sum("quantity")):
        sold[r["product_variant_id"]] = max(0, -r["q"])
    last_q = StockMovement.objects.filter(movement_type=T.SALE)
    if store_ids is not None:
        last_q = last_q.filter(store_id__in=list(store_ids))
    ids = set(on_hand) | {v for v, q in sold.items() if q}
    last = dict(last_q.filter(product_variant_id__in=ids).values_list("product_variant_id").annotate(m=Max("created_at")))
    costs = cost_map(ids)
    infos = stock.variant_infos(ids)
    rows = [Row(v, infos[v], on_hand.get(v, 0), sold.get(v, 0), last.get(v), costs.get(v) or Decimal(0), days) for v in ids if v in infos]

    # ABC by sales value at cost
    ranked = sorted((r for r in rows if r.sold), key=lambda r: r.sales_value or r.sold, reverse=True)
    total_sales = sum((r.sales_value for r in ranked), Decimal(0))
    running = Decimal(0)
    for r in ranked:
        share_before = running / total_sales if total_sales else Decimal(0)
        running += r.sales_value
        r.abc = "A" if share_before < Decimal("0.8") else "B" if share_before < Decimal("0.95") else "C"

    # flow by movement type (on-hand changes only)
    flow_q = moves.exclude(movement_type__in=(T.RESERVATION, T.RELEASE))
    if store_ids is None:
        flow_q = flow_q.exclude(movement_type__in=(T.TRANSFER_IN, T.TRANSFER_OUT))  # internal moves net to zero across locations
    flow_in, flow_out = {}, {}
    for r in flow_q.values("movement_type", "product_variant_id").annotate(pos=Sum("quantity", filter=Q(quantity__gt=0)), neg=Sum("quantity", filter=Q(quantity__lt=0))):
        cost = costs.get(r["product_variant_id"])
        if cost is None:
            cost = cost_map([r["product_variant_id"]]).get(r["product_variant_id"]) or Decimal(0)
            costs[r["product_variant_id"]] = cost
        for bucket, units in ((flow_in, r["pos"] or 0), (flow_out, -(r["neg"] or 0))):
            if units:
                b = bucket.setdefault(r["movement_type"], {"units": 0, "value": Decimal(0)})
                b["units"] += units
                b["value"] += cost * units

    stock_value = sum((r.value for r in rows), Decimal(0))
    cogs = sum((r.sales_value for r in rows), Decimal(0))
    per_day = cogs / days if days else Decimal(0)
    return {
        "rows": rows, "days": days,
        "stock_value": stock_value, "cogs": cogs, "units_sold": sum(r.sold for r in rows),
        "turnover": round(float(cogs / stock_value) * 365 / days, 1) if stock_value and days else None,
        "days_inventory": int(stock_value / per_day) if per_day else None,
        "dead": [r for r in rows if r.dead], "dead_value": sum((r.value for r in rows if r.dead), Decimal(0)),
        "loss_units": sum(v["units"] for k, v in flow_out.items() if k in LOSS), "loss_value": sum((v["value"] for k, v in flow_out.items() if k in LOSS), Decimal(0)),
        "flow_in": flow_in, "flow_out": flow_out,
        "abc": {k: {"n": sum(1 for r in ranked if r.abc == k), "value": sum((r.sales_value for r in ranked if r.abc == k), Decimal(0))} for k in "ABC"},
        "unpriced": sum(1 for r in rows if not r.cost),
    }
