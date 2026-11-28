"""
Abandoned-cart reminders: the one sender (Dashboard button, "remind all", the hourly automatic run) and the automatic
three-step sequence.

Automatic sequence for a signed-in customer's cart that still has products and produced no order -- the clock is the
cart's last change (`updated_at`), so adding or removing a product starts it again:

    step 1  2 h idle   "Savatingiz sizni kutyapti"            (kind cart_reminder)
    step 2  24 h idle  "Mahsulotlar hali savatda"              (kind cart_reminder_2, with the cart total)
    step 3  72 h idle  "Savol bo'lsa yordam beramiz" -- last   (kind cart_reminder_3)

Rules: at most one reminder per cart in 20 h (manual ones count too), nothing for carts idle over 7 days, nothing when
every product is sold out, nothing when the customer ordered since the cart changed (bot, phone, another cart), and
only between 10:00 and 21:59 Tashkent (the beat schedule). Telegram respects the customer's notification settings.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from apps.cart.infrastructure import models as orm

logger = logging.getLogger("nutrizone.app")

STEPS = ((1, 2, "cart_reminder"), (2, 24, "cart_reminder_2"), (3, 72, "cart_reminder_3"))  # (step, hours idle, kind)
MIN_GAP_HOURS = 20
MAX_IDLE_DAYS = 7
AUTO_BY = "Avtomatik"


def _summary(items) -> tuple[str, int, list]:
    from apps.cart.infrastructure.admin import _variant_cards

    cards = _variant_cards([i.product_variant_id for i in items])
    names = [cards[i.product_variant_id]["name"] for i in items if i.product_variant_id in cards]
    products = ", ".join(names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else "")
    total = sum(int((cards.get(i.product_variant_id) or {}).get("price") or 0) * int(i.quantity) for i in items)
    return products, total, names


def send(cart, items, *, by: str, kind: str = "cart_reminder", step: int | None = None) -> None:
    """One reminder: inbox + Telegram (notify) and a `reminder_sent` event in the cart history."""
    from apps.notifications.infrastructure.notify import fmt, notify

    products, total, _names = _summary(items)
    now = timezone.now()
    notify(cart.customer_id, kind, {"products": products, "total": fmt(total)}, link="/cart",
           dedupe_key=f"{kind}:{cart.id}:{now:%Y%m%d}")
    details = {"by": by, "kind": kind}
    if step:
        details["step"] = step
    orm.CartAuditEntryModel.objects.create(cart=cart, action="reminder_sent", actor_id=None, occurred_at=now, details=details)


def due_step(cart, reminders, now) -> tuple[int, str] | None:
    """The automatic step this cart should get now, or None. `reminders` = its reminder_sent entries (any order)."""
    idle = now - cart.updated_at
    if idle > timedelta(days=MAX_IDLE_DAYS):
        return None
    if any(r.occurred_at > now - timedelta(hours=MIN_GAP_HOURS) for r in reminders):
        return None
    done = max([(r.details or {}).get("step") or 0 for r in reminders if r.occurred_at >= cart.updated_at] or [0])
    # the latest step the cart is old enough for; a missed earlier one is skipped (a cart first seen at 30 h gets step 2)
    reached = [(s, k) for s, h, k in STEPS if idle >= timedelta(hours=h)]
    if not reached or reached[-1][0] <= done:
        return None
    return reached[-1]


def run_auto(now=None, limit: int = 300) -> dict:
    """The hourly pass. Returns counts per step (for the job log)."""
    from apps.cart.infrastructure.stock_guard import shortages
    from apps.ordering.infrastructure.models import OrderModel

    now = now or timezone.now()
    first = min(h for _s, h, _k in STEPS)
    carts = list(orm.CartModel.objects.filter(status="active", customer_id__isnull=False, items__status="active",
                                              updated_at__lt=now - timedelta(hours=first),
                                              updated_at__gte=now - timedelta(days=MAX_IDLE_DAYS))
                 .distinct().order_by("-updated_at")[:limit])
    if not carts:
        return {"checked": 0, "sent": 0}
    ids = [c.id for c in carts]
    ordered_carts = set(OrderModel.objects.filter(cart_id__in=ids).values_list("cart_id", flat=True))
    last_order = {}
    for cust, at in OrderModel.objects.exclude(status="draft").filter(customer_id__in={c.customer_id for c in carts}).values_list("customer_id", "created_at"):
        if cust not in last_order or at > last_order[cust]:
            last_order[cust] = at
    reminders: dict = {}
    for r in orm.CartAuditEntryModel.objects.filter(cart_id__in=ids, action="reminder_sent"):
        reminders.setdefault(r.cart_id, []).append(r)
    sent = {1: 0, 2: 0, 3: 0}
    for c in carts:
        if c.id in ordered_carts or (last_order.get(c.customer_id) and last_order[c.customer_id] >= c.updated_at):
            continue
        due = due_step(c, reminders.get(c.id, []), now)
        if not due:
            continue
        items = list(c.items.filter(status="active"))
        if not items:
            continue
        short = {s["product_variant_id"] for s in shortages([(i.product_variant_id, 1) for i in items]) if s["available"] <= 0}
        live = [i for i in items if str(i.product_variant_id) not in short]
        if not live:
            continue  # everything sold out -- a reminder would only disappoint
        try:
            send(c, live, by=AUTO_BY, kind=due[1], step=due[0])
            sent[due[0]] += 1
        except Exception:  # one bad cart never stops the pass
            logger.exception("cart.auto_remind: cart %s failed", c.id)
    result = {"checked": len(carts), "sent": sum(sent.values()), **{f"step{k}": v for k, v in sent.items()}}
    logger.info("cart.auto_remind: %s", result)
    return result
