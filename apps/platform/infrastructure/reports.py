"""
NutriZone Admin Reports & Business Intelligence -- aggregation layer
(Phase 08.8).

Calls only existing, already-certified selectors from their owning
bounded contexts. This module's own logic is limited to bookkeeping
and light shaping for template consumption -- it does not duplicate
any selector's own query/business logic, matching the exact
discipline already established by apps/platform/infrastructure/
dashboard_home.py (Phase 08.2).

Genuine, disclosed limitations (confirmed by direct reconnaissance,
not assumed):
- No Banner model exists -- no Banner analytics.
- No customer segmentation model exists -- no segment-based reports.
- Order has no store_id -- no store-scoped sales report.
- No Review moderation Application Services exist -- no moderation
  analytics.
- Inventory "value" is not calculated: no certified valuation source
  (quantity x price) exists connecting Inventory to Pricing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal


def _percentage_change(current: Decimal, previous: Decimal) -> dict:
    """Reused verbatim from dashboard_home.py's own established convention: None (never 0 or a fabricated value) when there is no previous-period baseline."""
    if previous == 0:
        return {"value": None, "direction": None}
    change = ((current - previous) / previous) * 100
    return {"value": round(float(change), 1), "direction": "up" if change > 0 else ("down" if change < 0 else "flat")}


@dataclass(slots=True)
class ReportPeriod:
    label: str
    current_start: datetime
    current_end: datetime
    previous_start: datetime
    previous_end: datetime

    @classmethod
    def last_n_days(cls, n: int, label: str) -> "ReportPeriod":
        now = datetime.now(timezone.utc)
        current_start = now - timedelta(days=n)
        previous_start = current_start - timedelta(days=n)
        return cls(label=label, current_start=current_start, current_end=now, previous_start=previous_start, previous_end=current_start)


class ReportsAggregator:
    """One aggregation pass per Reports page request.

    Money follows the Analitika formula (business_analytics): Tashkent calendar days, kept till receipts +
    delivered/completed online orders by the day the customer placed them, a running period compared with the same
    elapsed span before it -- so Reports, Biznes analitikasi, the home page and the analytics bot agree. (Until
    2026-11-16 this page counted only online orders in status "completed" and showed 0 while the business sold.)
    """

    def __init__(self, period: ReportPeriod, range_key: str | None = None) -> None:
        self._period = period
        self._range_key = range_key
        self._cache: dict = {}

    # ------------------------------------------------------------ shared period data
    def _ba(self):
        if "ba" not in self._cache:
            from apps.platform.infrastructure import business_analytics as ba

            if self._range_key:
                bp = ba.period(self._range_key)
            else:  # an explicit ReportPeriod (tests, exports): the same window, Analitika formula
                p = self._period
                bp = ba.Period("custom", "", p.current_start, p.current_end, p.previous_start, p.previous_end, "oldingi davrga nisbatan", True)
            cur, prev = ba._base(bp.start, bp.end), ba._base(bp.prev_start, bp.prev_end)
            self._cache["ba"] = (ba, bp, cur, prev)
        return self._cache["ba"]

    def _lines(self):
        if "lines" not in self._cache:
            ba, _bp, cur, _prev = self._ba()
            self._cache["lines"] = ba._sold_lines(cur)
        return self._cache["lines"]

    def period_info(self) -> dict:
        _ba, bp, _cur, _prev = self._ba()
        return {"key": bp.key, "title": bp.title, "range": bp.range_text() if bp.title else "", "compare": bp.compare_label}

    def sales_report(self) -> dict:
        ba, _bp, cur, prev = self._ba()
        revenue, prev_revenue = cur["revenue"], prev["revenue"]
        orders, prev_orders = cur["purchases"], prev["purchases"]
        avg = (revenue / orders) if orders else Decimal("0")
        prev_avg = (prev_revenue / prev_orders) if prev_orders else Decimal("0")
        statuses: dict = {}
        for o in cur["online"]:
            statuses[o["status"]] = statuses.get(o["status"], 0) + 1
        return {
            "gross_sales": revenue,
            "revenue_change": _percentage_change(revenue, prev_revenue),
            "previous_revenue": prev_revenue,
            "orders": orders,
            "orders_change": _percentage_change(Decimal(orders), Decimal(prev_orders)),
            "cancelled_orders": sum(1 for o in cur["online"] if o["status"] in ("cancelled", "failed")),
            "average_order_value": avg.quantize(Decimal("1")) if avg else avg,
            "average_change": _percentage_change(avg, prev_avg),
            "online_revenue": cur["online_revenue"], "pos_revenue": cur["pos_revenue"],
            "online_orders": len(cur["earned"]), "pos_sales": orders - len(cur["earned"]),
            "units": cur["units"], "refunds_total": cur["refunds_total"], "refunds_count": cur["refunds_count"],
            "discounts": cur["discounts"], "pipeline_orders": cur["pipeline_orders"], "pipeline_value": cur["pipeline_value"],
            "lost_orders": cur["lost_orders"], "lost_value": cur["lost_value"],
            "order_status_distribution": statuses,
        }

    def profit_report(self) -> dict:
        ba, _bp, cur, _prev = self._ba()
        return ba._cost(self._lines(), cur["revenue"])

    def payments_report(self) -> dict:
        ba, _bp, cur, _prev = self._ba()
        return ba._payments(cur)

    def orders_report(self) -> dict:
        ba, _bp, cur, prev = self._ba()
        return ba._orders(cur, prev)

    def mix_report(self) -> dict:
        ba, _bp, _cur, _prev = self._ba()
        return ba._mix(self._lines())

    def top_sellers(self, limit: int = 10) -> list[dict]:
        ba, _bp, _cur, _prev = self._ba()
        return ba.top_products(self._lines(), limit)

    def buyers_report(self) -> dict:
        ba, bp, cur, _prev = self._ba()
        return ba._customers(bp, cur)

    def regions_report(self) -> dict:
        from apps.platform.infrastructure import regions_report

        _ba, bp, _cur, _prev = self._ba()
        data = regions_report.report(bp.key if bp.key != "custom" else "30d")
        return {"summary": data["summary"], "rows": [r for r in data["regions"] if r["orders"]][:8]}

    def customer_report(self) -> dict:
        from apps.identity.infrastructure.selectors import UserStatisticsSelector

        selector = UserStatisticsSelector()
        return {"total_customers": selector.total_customers(), "counts_by_status": selector.counts_by_status()}

    def product_report(self) -> dict:
        from apps.products.infrastructure.selectors import StatisticsSelector as ProductStatisticsSelector

        selector = ProductStatisticsSelector()
        top = [{"name": f"{t['name']} {t['size']}".strip(), "sku": t["sku"], "units": t["units"], "revenue": t["revenue"]} for t in self.top_sellers(10)]
        return {"counts_by_status": selector.counts_by_status(), "top_products": top, "products_by_category": selector.products_by_category(limit=8)}

    def inventory_report(self) -> dict:
        """Inventory 'value' is deliberately not calculated -- no certified source connects Inventory quantities to Pricing amounts (a genuine, disclosed limitation, not an oversight)."""
        from apps.platform.infrastructure.dashboard_home import wms_low_stock

        items = wms_low_stock()
        out_of_stock = sum(1 for item in items if item["available_quantity"] == 0)
        return {"low_stock_total": len(items), "out_of_stock_total": out_of_stock}

    def marketing_report(self) -> dict:
        from apps.pricing.infrastructure.selectors import MarketingStatisticsSelector

        from django.utils.translation import gettext as _t

        selector = MarketingStatisticsSelector()
        return {
            "statuses_label": {"active": _t("faol"), "inactive": _t("nofaol"), "expired": _t("muddati o'tgan"), "draft": _t("qoralama"), "scheduled": _t("rejalashtirilgan"), "paused": _t("to'xtatilgan"), "ended": _t("tugagan")},
            "coupon_counts_by_status": selector.coupon_counts_by_status(),
            "campaign_counts_by_status": selector.campaign_counts_by_status(),
            "total_redemptions": selector.total_redemptions(),
        }

    def review_report(self) -> dict:
        from apps.reviews.infrastructure.selectors import ReviewStatisticsSelector

        from django.utils.translation import gettext as _t

        labels = {"published": _t("Chop etilgan"), "approved": _t("Tasdiqlangan"), "draft": _t("Qoralama"), "pending": _t("Kutilmoqda"),
                  "rejected": _t("Rad etilgan"), "hidden": _t("Yashirilgan"), "flagged": _t("Shikoyat qilingan")}
        counts = ReviewStatisticsSelector().counts_by_status()
        return {"counts_by_status": counts, "statuses": [{"code": k, "label": labels.get(k, k), "count": v} for k, v in counts.items()]}
