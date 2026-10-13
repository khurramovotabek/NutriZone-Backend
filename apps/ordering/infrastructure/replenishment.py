"""
Qayta to'ldirish -- "your protein is about to run out": predicts, per customer and product, when what they bought
will be used up, and reminds them a few days before, so the next tub arrives in time.

How long one purchase lasts (`supply_days`):
  1. their own rhythm -- with 2+ purchases of the product, the median gap between them (the best signal there is);
  2. otherwise the product's servings: quantity x servings per container / SERVINGS_PER_DAY;
  3. otherwise DEFAULT_DAYS_PER_UNIT per unit.
Clamped to MIN_DAYS..MAX_DAYS. Counted from when they got it: delivered (online) or the sale (store / POS).

A reminder goes out once per purchase (dedupe key), LEAD_DAYS before the predicted end and up to GRACE_DAYS after
it -- never when they already bought it again, the product is no longer sold, or nothing is in stock.
"""
from __future__ import annotations

import statistics
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

SERVINGS_PER_DAY = 1
DEFAULT_DAYS_PER_UNIT = 30
MIN_DAYS, MAX_DAYS = 10, 180
LEAD_DAYS = 5
GRACE_DAYS = 14
LOOKBACK_DAYS = 365
EARNED_ORDER_STATUSES = ("delivered", "completed")


@dataclass
class Purchase:
    customer_id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    quantity: int
    at: datetime
    ref: str  # "order:<id>" / "sale:<id>" -- the reminder's dedupe identity


@dataclass
class Forecast:
    customer_id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID | None
    last_at: datetime
    supply_days: int
    basis: str  # "history" | "servings" | "default"
    ref: str

    @property
    def runs_out_at(self) -> datetime:
        return self.last_at + timedelta(days=self.supply_days)

    def days_left(self, now: datetime | None = None) -> int:
        return (self.runs_out_at - (now or timezone.now())).days


def purchases(customer_ids=None, since: datetime | None = None) -> list[Purchase]:
    """Every product a customer received in the lookback window -- online orders (delivered) and store sales."""
    from apps.ordering.infrastructure.models import OrderLineItemModel, OrderStatusHistoryEntryModel
    from apps.pos.infrastructure.models import SaleLineItemModel
    from apps.products.infrastructure.models import ProductVariant

    since = since or timezone.now() - timedelta(days=LOOKBACK_DAYS)
    out: list[Purchase] = []

    lines = OrderLineItemModel.objects.filter(order__status__in=EARNED_ORDER_STATUSES, order__customer_id__isnull=False, order__created_at__gte=since).exclude(status="cancelled")
    if customer_ids is not None:
        lines = lines.filter(order__customer_id__in=list(customer_ids))
    rows = list(lines.values("order_id", "order__customer_id", "order__placed_at", "order__created_at", "product_variant_id", "quantity"))
    product_of = dict(ProductVariant.all_objects.filter(id__in={r["product_variant_id"] for r in rows}).values_list("id", "product_id"))
    received = {}
    for order_id, changed_at in OrderStatusHistoryEntryModel.objects.filter(order_id__in={r["order_id"] for r in rows}, to_status__in=EARNED_ORDER_STATUSES).order_by("changed_at").values_list("order_id", "changed_at"):
        received.setdefault(order_id, changed_at)  # the first delivered/completed moment
    for r in rows:
        product_id = product_of.get(r["product_variant_id"])
        if product_id:
            at = received.get(r["order_id"]) or r["order__placed_at"] or r["order__created_at"]
            out.append(Purchase(r["order__customer_id"], product_id, r["product_variant_id"], r["quantity"], at, f"order:{r['order_id']}"))

    sale_lines = SaleLineItemModel.objects.filter(sale__status="completed", sale__customer_id__isnull=False, sale__completed_at__gte=since)
    if customer_ids is not None:
        sale_lines = sale_lines.filter(sale__customer_id__in=list(customer_ids))
    for r in sale_lines.values("sale_id", "sale__customer_id", "sale__completed_at", "product_id", "product_variant_id", "quantity", "refunded_quantity"):
        kept = r["quantity"] - (r["refunded_quantity"] or 0)
        if kept > 0:
            out.append(Purchase(r["sale__customer_id"], r["product_id"], r["product_variant_id"], kept, r["sale__completed_at"], f"sale:{r['sale_id']}"))
    return out


def _clamp(days: float) -> int:
    return int(max(MIN_DAYS, min(MAX_DAYS, round(days))))


def forecasts(customer_ids=None, now: datetime | None = None) -> list[Forecast]:
    """One forecast per (customer, product): when the latest purchase of it runs out."""
    from apps.products.infrastructure.models import Product

    groups: dict[tuple, list[Purchase]] = {}
    for p in purchases(customer_ids):
        groups.setdefault((p.customer_id, p.product_id), []).append(p)
    servings = dict(Product.objects.filter(id__in={k[1] for k in groups}).values_list("id", "nutrition_servings_per_container"))

    out = []
    for (customer_id, product_id), items in groups.items():
        # one "visit" = one order / sale; several lines of the product in it count together
        visits: dict[str, tuple[datetime, int]] = {}
        for p in items:
            at, qty = visits.get(p.ref, (p.at, 0))
            visits[p.ref] = (min(at, p.at), qty + p.quantity)
        ordered = sorted(visits.items(), key=lambda kv: kv[1][0])
        last_ref, (last_at, quantity) = ordered[-1]
        # their own pace: days one unit lasted, between consecutive purchases (gaps under 3 days are one restock)
        per_unit = [(b[0] - a[0]).total_seconds() / 86400 / a[1] for (_, a), (_, b) in zip(ordered, ordered[1:]) if (b[0] - a[0]).days >= 3]
        if per_unit:
            days, basis = statistics.median(per_unit) * quantity, "history"
        elif servings.get(product_id):
            days, basis = quantity * servings[product_id] / SERVINGS_PER_DAY, "servings"
        else:
            days, basis = quantity * DEFAULT_DAYS_PER_UNIT, "default"
        variant_id = next((p.variant_id for p in reversed(items) if p.ref == last_ref), None)
        out.append(Forecast(customer_id, product_id, variant_id, last_at, _clamp(days), basis, last_ref))
    return out


def due(now: datetime | None = None, customer_ids=None) -> list[Forecast]:
    """Forecasts to remind about today: within LEAD_DAYS of running out (or up to GRACE_DAYS past), product still sold and in stock."""
    from apps.products.infrastructure.models import Product, ProductVariant
    from apps.stores.infrastructure.availability import sellable

    now = now or timezone.now()
    window = [f for f in forecasts(customer_ids, now) if -GRACE_DAYS <= f.days_left(now) <= LEAD_DAYS]
    if not window:
        return []
    published = set(Product.objects.filter(id__in={f.product_id for f in window}, status="published").values_list("id", flat=True))
    variants_by_product: dict = {}
    for vid, pid in ProductVariant.objects.filter(product_id__in=published).values_list("id", "product_id"):
        variants_by_product.setdefault(pid, []).append(vid)
    stock = sellable([v for vs in variants_by_product.values() for v in vs])
    return [f for f in window if f.product_id in published and any(stock.get(v, 0) > 0 for v in variants_by_product.get(f.product_id, []))]
