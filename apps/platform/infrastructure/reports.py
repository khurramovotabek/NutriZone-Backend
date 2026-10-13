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
    """One aggregation pass per Reports page request. Every selector call below is read-only and already exists in its own bounded context (or is this phase's own minimal, disclosed selector extension)."""

    def __init__(self, period: ReportPeriod) -> None:
        self._period = period

    def sales_report(self) -> dict:
        """Reuses OrderStatisticsSelector.total_revenue_by_status() (Phase 08.2's own date-range extension) and OrderModel counts directly -- the exact same formula already certified for the Dashboard Home KPI, not a second calculation."""
        from apps.ordering.infrastructure.selectors import OrderStatisticsSelector
        from apps.ordering.infrastructure import models as ordering_orm

        order_stats = OrderStatisticsSelector()
        p = self._period

        current_revenue = Decimal(order_stats.total_revenue_by_status("completed", date_from=p.current_start, date_to=p.current_end).get("UZS", "0"))
        previous_revenue = Decimal(order_stats.total_revenue_by_status("completed", date_from=p.previous_start, date_to=p.previous_end).get("UZS", "0"))

        current_orders = ordering_orm.OrderModel.objects.filter(status="completed", created_at__gte=p.current_start, created_at__lt=p.current_end).count()
        previous_orders = ordering_orm.OrderModel.objects.filter(status="completed", created_at__gte=p.previous_start, created_at__lt=p.previous_end).count()
        cancelled_orders = ordering_orm.OrderModel.objects.filter(status="cancelled", created_at__gte=p.current_start, created_at__lt=p.current_end).count()

        avg_order_value = (current_revenue / current_orders) if current_orders else Decimal("0")

        return {
            "gross_sales": current_revenue,
            "revenue_change": _percentage_change(current_revenue, previous_revenue),
            "orders": current_orders,
            "orders_change": _percentage_change(Decimal(current_orders), Decimal(previous_orders)),
            "cancelled_orders": cancelled_orders,
            "average_order_value": avg_order_value,
            "order_status_distribution": order_stats.counts_by_status(),
        }

    def customer_report(self) -> dict:
        from apps.identity.infrastructure.selectors import UserStatisticsSelector

        selector = UserStatisticsSelector()
        return {"total_customers": selector.total_customers(), "counts_by_status": selector.counts_by_status()}

    def product_report(self) -> dict:
        from apps.products.infrastructure.selectors import StatisticsSelector as ProductStatisticsSelector

        selector = ProductStatisticsSelector()
        return {"counts_by_status": selector.counts_by_status(), "top_products": selector.top_products(limit=10), "products_by_category": selector.products_by_category(limit=8)}

    def inventory_report(self) -> dict:
        """Inventory 'value' is deliberately not calculated -- no certified source connects Inventory quantities to Pricing amounts (a genuine, disclosed limitation, not an oversight)."""
        from apps.platform.infrastructure.dashboard_home import wms_low_stock

        items = wms_low_stock()
        out_of_stock = sum(1 for item in items if item["available_quantity"] == 0)
        return {"low_stock_total": len(items), "out_of_stock_total": out_of_stock}

    def marketing_report(self) -> dict:
        from apps.pricing.infrastructure.selectors import MarketingStatisticsSelector

        selector = MarketingStatisticsSelector()
        return {
            "coupon_counts_by_status": selector.coupon_counts_by_status(),
            "campaign_counts_by_status": selector.campaign_counts_by_status(),
            "total_redemptions": selector.total_redemptions(),
        }

    def review_report(self) -> dict:
        from apps.reviews.infrastructure.selectors import ReviewStatisticsSelector

        return {"counts_by_status": ReviewStatisticsSelector().counts_by_status()}
