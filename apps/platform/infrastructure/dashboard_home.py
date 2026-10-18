"""
NutriZone Admin Dashboard Home -- aggregation layer (Phase 08.2).

Calls only existing, already-certified selectors from their owning
bounded contexts (Ordering, Identity, Products, Inventory). This
module's own logic is limited to: (1) date-range bookkeeping for
period-over-period comparison, (2) simple arithmetic on numbers those
selectors already returned (percentage change, average order value),
and (3) shaping results for template consumption. It does not
duplicate any selector's own query logic.

Architectural note (Phase 08.2's own scope decision, disclosed): Order
has no store_id field (confirmed by direct inspection) -- store-level
filtering is not implemented here, since the underlying data model
does not support it. Building a store filter against non-existent
data would mean fabricating scoping that doesn't exist.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal


def _percentage_change(current: Decimal, previous: Decimal) -> dict:
    """None (not 0 or inf) when there is no previous-period baseline to compare against -- avoids both a division-by-zero crash and a misleading fabricated percentage."""
    if previous == 0:
        return {"value": None, "direction": None}
    change = ((current - previous) / previous) * 100
    return {"value": round(float(change), 1), "direction": "up" if change > 0 else ("down" if change < 0 else "flat")}


@dataclass(slots=True)
class DashboardPeriod:
    label: str
    current_start: datetime
    current_end: datetime
    previous_start: datetime
    previous_end: datetime

    @classmethod
    def last_n_days(cls, n: int, label: str) -> "DashboardPeriod":
        now = datetime.now(timezone.utc)
        current_start = now - timedelta(days=n)
        previous_start = current_start - timedelta(days=n)
        return cls(label=label, current_start=current_start, current_end=now, previous_start=previous_start, previous_end=current_start)


def wms_low_stock() -> list[dict]:
    """
    Products at or below their reorder minimum, from the WMS (StoreProductStock + ReorderRule -- the stock truth;
    the old inventory mirror is no longer written). Projected = available + incoming transfers, as on the
    To'ldirish page; empty shelves first, then the thinnest cover.
    """
    from apps.stores.infrastructure import planning_service as plan
    from apps.stores.infrastructure import stock_service as stock
    from apps.stores.infrastructure.models import ReorderRule, Store

    out = []
    for store in Store.objects.exclude(status="inactive"):
        rules = list(ReorderRule.objects.filter(store=store).select_related("product_variant"))
        if not rules:
            continue
        ids = [r.product_variant_id for r in rules]
        avail, incoming = stock.available_map(store, ids), plan.incoming_map(store, ids)
        for r in rules:
            have = avail.get(r.product_variant_id, 0)
            if have + incoming.get(r.product_variant_id, 0) <= r.min_quantity:
                out.append({"code": f"{r.product_variant.sku} · {store.name}", "available_quantity": have, "low_stock_at": r.min_quantity, "store_id": str(store.id)})
    out.sort(key=lambda i: (i["available_quantity"] > 0, i["available_quantity"] / max(i["low_stock_at"], 1)))
    return out


class DashboardHomeAggregator:
    """One aggregation pass per dashboard-home request. Every selector call below is read-only and already exists in its own bounded context -- see this module's own docstring."""

    def __init__(self, period: DashboardPeriod) -> None:
        self._period = period
        self._low_stock_cache = None

    def _low_stock(self, page_size: int = 1000):
        """Memoized per-instance -- kpis() and low_stock_alerts() both need this, and one aggregator instance serves exactly one dashboard request, so caching here avoids a duplicate query without introducing any cross-request state."""
        if self._low_stock_cache is None:
            items = wms_low_stock()
            self._low_stock_cache = items[:page_size], len(items)
        return self._low_stock_cache

    def kpis(self) -> dict:
        """
        Sales KPIs with the Analitika formula (business_analytics): Tashkent calendar days, till receipts +
        delivered/completed online orders by placed_at, a running period compared with the same elapsed span
        before it -- so the home page, the Analitika page and the analytics bot show the same numbers.
        """
        from apps.identity.infrastructure.selectors import UserStatisticsSelector
        from apps.platform.infrastructure import business_analytics as ba
        from apps.products.infrastructure.selectors import StatisticsSelector as ProductStatisticsSelector

        p = self._period
        days = max(1, round((p.current_end - p.current_start).total_seconds() / 86400))
        bp = ba.period("7d" if days <= 7 else "30d")
        cur, prev = ba._base(bp.start, bp.end), ba._base(bp.prev_start, bp.prev_end)

        current_revenue, previous_revenue = cur["revenue"], prev["revenue"]
        current_order_count, previous_order_count = cur["purchases"], prev["purchases"]
        avg_order_value = (current_revenue / current_order_count) if current_order_count else Decimal("0")
        previous_avg = (previous_revenue / previous_order_count) if previous_order_count else Decimal("0")

        product_counts = ProductStatisticsSelector().counts_by_status()
        low_stock_items, low_stock_total = self._low_stock()
        out_of_stock_total = sum(1 for item in low_stock_items if item["available_quantity"] == 0)

        return {
            "range": bp.title,
            "revenue": {"current": current_revenue, "change": _percentage_change(current_revenue, previous_revenue)},
            "online_revenue": cur["online_revenue"],
            "pos_revenue": cur["pos_revenue"],
            "orders": {"current": current_order_count, "change": _percentage_change(Decimal(current_order_count), Decimal(previous_order_count))},
            "online_orders": len(cur["earned"]),
            "pos_sales": current_order_count - len(cur["earned"]),
            "pipeline_orders": cur["pipeline_orders"],
            "pipeline_value": cur["pipeline_value"],
            "customers_total": UserStatisticsSelector().total_customers(),
            "products_total": sum(product_counts.values()),
            "products_active": product_counts.get("published", 0),
            "products_inactive": sum(v for k, v in product_counts.items() if k != "published"),
            "average_order_value": avg_order_value,
            "average_change": _percentage_change(avg_order_value, previous_avg),
            "low_stock_total": low_stock_total,
            "out_of_stock_total": out_of_stock_total,
        }

    def revenue_series(self, days: int = 7) -> list[dict]:
        """Daily completed-order revenue for the last N days -- reuses total_revenue_by_status's own certified formula per day, one query per day (bounded, small N, never per-order)."""
        from apps.ordering.infrastructure.selectors import OrderStatisticsSelector

        order_stats = OrderStatisticsSelector()
        now = datetime.now(timezone.utc)
        series = []
        for i in range(days - 1, -1, -1):
            day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            revenue_by_ccy = order_stats.total_revenue_by_status("completed", date_from=day_start, date_to=day_end)
            series.append({"date": day_start.strftime("%Y-%m-%d"), "revenue": float(Decimal(revenue_by_ccy.get("UZS", "0")))})
        return series

    def top_products(self, limit: int = 5) -> list[dict]:
        from apps.products.infrastructure.selectors import StatisticsSelector as ProductStatisticsSelector

        return ProductStatisticsSelector().top_products(limit=limit)

    def recent_orders(self, limit: int = 8) -> list[dict]:
        from apps.ordering.infrastructure.selectors import OrderSelector

        rows, _total = OrderSelector().list(status=None, customer_id=None, page=1, page_size=limit)
        return rows

    def low_stock_alerts(self, limit: int = 5) -> list[dict]:
        items, _total = self._low_stock()
        return items[:limit]

    def order_status_distribution(self) -> dict:
        from apps.ordering.infrastructure.selectors import OrderStatisticsSelector

        return OrderStatisticsSelector().counts_by_status()
