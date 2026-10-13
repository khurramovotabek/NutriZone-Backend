"""
"Bugungi vazifalar" -- the dashboard home's action centre: every queue across the modules that is waiting on a
person, as one ranked list (most urgent first), each linking straight to the filtered page that resolves it.

Each queue is computed on its own and a failing one is skipped (logged), so one module's outage never hides the
others. Only non-empty queues are shown; an empty list renders the "all clear" state.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger("nutrizone.app")

URGENT, HIGH, NORMAL = 0, 1, 2
EXPIRY_DAYS = 30


@dataclass
class Task:
    key: str
    label: str
    count: int
    hint: str
    url: str
    icon: str
    tone: str
    priority: int = NORMAL


def _orders() -> list[Task]:
    from apps.ordering.infrastructure.admin import LATE_HOURS, late_orders
    from apps.ordering.infrastructure.models import OrderModel

    base = reverse("admin:ordering_ordermodel_changelist")
    live = OrderModel.objects.filter(is_archived=False)
    out = []
    new = live.filter(status="confirmed").count()
    if new:
        out.append(Task("orders_new", "Yangi buyurtmalar", new, "tasdiqlangan — yig'ishni boshlang", f"{base}?status=confirmed", "fa-inbox", "#2563eb", HIGH))
    late = late_orders(OrderModel.objects.all()).count()
    if late:
        out.append(Task("orders_late", "Kechikayotgan buyurtmalar", late, f"{LATE_HOURS} soatdan beri harakatsiz", f"{base}?late=1", "fa-hourglass-half", "#e11d48", URGENT))
    return out


def _chats() -> list[Task]:
    from apps.platform.infrastructure.chat_view import _waiting_ids

    n = len(_waiting_ids())
    return [Task("chats", "Javob kutayotgan chatlar", n, "mijoz oxirgi bo'lib yozgan", reverse("admin:nz_chat_admin"), "fa-comments", "#e11d48" if n >= 3 else "#f59e0b", URGENT if n >= 3 else HIGH)] if n else []


def _after_sales() -> list[Task]:
    from apps.ordering.infrastructure.models import OrderCancellationModel, OrderReturnModel

    out = []
    n = OrderCancellationModel.objects.filter(status="requested").count()
    if n:
        out.append(Task("cancellations", "Bekor qilish so'rovlari", n, "mijoz javob kutyapti", reverse("admin:ordering_ordercancellationmodel_changelist") + "?status__exact=requested", "fa-ban", "#e11d48", URGENT))
    n = OrderReturnModel.objects.filter(status="requested").count()
    if n:
        out.append(Task("returns", "Qaytarish so'rovlari", n, "ko'rib chiqilmagan", reverse("admin:ordering_orderreturnmodel_changelist") + "?status__exact=requested", "fa-rotate-left", "#f59e0b", HIGH))
    return out


def _reviews() -> list[Task]:
    from apps.reviews.infrastructure.models import ReviewModel

    n = ReviewModel.objects.filter(status="pending_moderation").count()
    return [Task("reviews", "Moderatsiyadagi sharhlar", n, "tasdiqlansa saytda chiqadi", reverse("admin:reviews_reviewmodel_changelist") + "?status__exact=pending_moderation", "fa-star-half-stroke", "#9333ea")] if n else []


def _contact() -> list[Task]:
    from apps.platform.infrastructure.models import ContactMessage, ContactMessageStatus

    n = ContactMessage.objects.filter(status=ContactMessageStatus.NEW).count()
    return [Task("contact", "Yangi murojaatlar", n, "kontakt formasi orqali", reverse("admin:platform_contactmessage_changelist") + "?status__exact=new", "fa-envelope", "#0891b2")] if n else []


def _stock() -> list[Task]:
    from apps.platform.infrastructure.dashboard_home import wms_low_stock

    items = wms_low_stock()
    if not items:
        return []
    empty = sum(1 for i in items if i["available_quantity"] == 0)
    return [Task("stock", "To'ldirish kerak", len(items), f"{empty} tasi tugagan" if empty else "minimal qoldiqdan past",
                 reverse("admin:stores_reorderrule_changelist"), "fa-boxes-stacked", "#e11d48" if empty else "#f59e0b", URGENT if empty else HIGH)]


def _expiry() -> list[Task]:
    from apps.stores.infrastructure import planning_service as plan

    today = timezone.localdate()
    soon = [ly for ly in plan.layers() if ly.expiry and 0 <= (ly.expiry - today).days <= EXPIRY_DAYS]
    if not soon:
        return []
    units = sum(ly.quantity for ly in soon)
    return [Task("expiry", "Muddati yaqin mahsulotlar", units, f"{EXPIRY_DAYS} kun ichida tugaydi — chegirma bilan soting", reverse("admin:nz_wms_expiry"), "fa-calendar-xmark", "#ea580c", HIGH)]


def _payments() -> list[Task]:
    from apps.payment.infrastructure.models import PaymentReconciliationIssue, ReconciliationStatus

    n = PaymentReconciliationIssue.objects.filter(status=ReconciliationStatus.OPEN).count()
    return [Task("payments", "To'lov nomuvofiqliklari", n, "provayder bilan solishtirish kerak", reverse("admin:payment_paymentreconciliationissue_changelist"), "fa-scale-unbalanced", "#e11d48", URGENT)] if n else []


def _missed_searches() -> list[Task]:
    """Terms shoppers searched this week that found nothing -- demand to stock for, or a missing product name/synonym."""
    from datetime import timedelta

    from apps.search.infrastructure.models import SearchTerm

    rows = list(SearchTerm.objects.filter(last_results=0, last_seen__gte=timezone.now() - timedelta(days=7)).order_by("-searches").values_list("display", flat=True)[:3])
    if not rows:
        return []
    n = SearchTerm.objects.filter(last_results=0, last_seen__gte=timezone.now() - timedelta(days=7)).count()
    return [Task("missed_searches", "Topilmagan qidiruvlar", n, ", ".join(f"«{r}»" for r in rows), reverse("admin:search_searchterm_changelist") + "?nz=missing", "fa-magnifying-glass-minus", "#0891b2")]


SOURCES = (_orders, _chats, _after_sales, _payments, _stock, _expiry, _reviews, _contact, _missed_searches)


def build() -> dict:
    tasks: list[Task] = []
    failed = 0
    for source in SOURCES:
        try:
            tasks.extend(source())
        except Exception:  # noqa: BLE001 - one module's queue never hides the rest
            failed += 1
            logger.exception("Dashboard task source %s failed", source.__name__)
    tasks.sort(key=lambda t: (t.priority, -t.count))
    return {"tasks": tasks, "urgent": sum(1 for t in tasks if t.priority == URGENT), "total": sum(t.count for t in tasks), "failed": failed}
