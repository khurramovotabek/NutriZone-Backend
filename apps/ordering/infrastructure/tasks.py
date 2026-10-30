"""
Ordering Celery tasks -- orchestration only, idempotent, dead-letter
safe. Every task loads data, calls a real Application Service for the
actual decision, and persists/reports the result -- never business
logic itself. Each task's per-item try/except means one failure never
aborts the sweep for the rest (the failed item simply gets picked up
again on the next scheduled run -- naturally idempotent, no explicit
dead-letter queue needed since `ExpireOrder`/`ArchiveCart`-equivalent
operations are themselves idempotent at the domain level: expiring an
already-expired order or re-running the sweep against it is a no-op
guarded by the aggregate's own status checks).
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone as django_timezone

from apps.ordering.infrastructure import models as orm
from apps.ordering.infrastructure.event_handlers import handle_ordering_event
from core.outbox import OutboxRelay


@shared_task(queue="scheduled", name="ordering.expire_orders")
def expire_orders() -> int:
    """Sweeps every DRAFT/PENDING_PAYMENT order past its 2-hour expiry window and calls the real `ExpireOrder` Application Service for each."""
    import uuid

    from apps.ordering.infrastructure.composition import build_expire_order
    from apps.ordering.infrastructure.selectors import ExpiringOrderSelector

    expiring = ExpiringOrderSelector().list_expiring()
    count = 0
    for entry in expiring:
        try:
            build_expire_order().execute(uuid.UUID(entry["id"]))
            count += 1
        except Exception:  # noqa: BLE001 - one failure must not abort the sweep for the rest
            continue
    return count


@shared_task(queue="scheduled", name="ordering.cleanup_stale_return_requests")
def cleanup_stale_return_requests(older_than_days: int = 30) -> int:
    """Flags (via a metric, not an automatic rejection) return requests stuck in REQUESTED for too long -- a genuine business decision (reject vs. escalate) that stays with a human, this task only surfaces the count for ops visibility."""
    from datetime import timedelta

    cutoff = django_timezone.now() - timedelta(days=older_than_days)
    count = orm.OrderReturnModel.objects.filter(status="requested", requested_at__lte=cutoff).count()
    if count:
        from core.metrics import default_collector

        default_collector.counter("stale_return_requests_total", count)
    return count


@shared_task(queue="scheduled", name="ordering.rebuild_statistics")
def rebuild_statistics() -> str:
    from apps.ordering.infrastructure.event_handlers import invalidate_ordering_cache_group

    invalidate_ordering_cache_group("order_list")
    return "ok"


@shared_task(queue="transactional", name="ordering.relay_outbox_events")
def relay_outbox_events() -> dict:
    """Celery Beat-scheduled Outbox relay for the `ordering` schema -- matches every prior module's identical relay task."""

    def _publish(event) -> bool:
        try:
            handle_ordering_event(event.event_type, event.payload)
            return True
        except Exception:  # noqa: BLE001
            return False

    relay = OutboxRelay(orm.OrderingOutboxEvent, max_attempts=5, batch_size=100)
    return relay.relay_pending(publish_fn=_publish)


_DAYS_TEXT = {
    "uz": ("taxminan {n} kundan keyin tugaydi", "tugagan bo'lishi mumkin"),
    "ru": ("закончится примерно через {n} дн.", "возможно, уже закончился"),
    "en": ("will run out in about {n} days", "may already have run out"),
}


@shared_task(queue="default", name="ordering.replenish_reminders")
def replenish_reminders() -> int:
    """Daily: "your {product} is running low" for every purchase predicted to run out soon (replenishment.py). One per purchase."""
    from apps.notifications.infrastructure.notify import notify
    from apps.ordering.infrastructure.replenishment import due
    from apps.products.infrastructure.models import ProductTranslation

    forecasts = due()
    names: dict = {}
    slugs: dict = {}
    for pid, locale, name, slug in ProductTranslation.objects.filter(product_id__in={f.product_id for f in forecasts}).values_list("product_id", "locale_code", "name", "slug"):
        names.setdefault(pid, {})[locale] = name
        if slug and (locale == "uz" or pid not in slugs):
            slugs[pid] = slug
    sent = 0
    for f in forecasts:
        product_names = names.get(f.product_id) or {}
        fallback = product_names.get("uz") or next(iter(product_names.values()), "")
        days = f.days_left()
        i18n = {lang: {"product": product_names.get(lang) or fallback, "days_text": (soon.format(n=max(days, 1)) if days > 0 else gone)} for lang, (soon, gone) in _DAYS_TEXT.items()}
        notify(f.customer_id, "replenish_reminder", {"product": fallback, "days_text": i18n["uz"]["days_text"], "i18n": i18n},
               link=f"/products/{slugs[f.product_id]}" if f.product_id in slugs else "/orders", dedupe_key=f"replenish:{f.ref}:{f.product_id}")
        sent += 1
    return sent


_MORE_TEXT = {"uz": " va yana {n} ta mahsulot", "ru": " и ещё {n} товар(ов)", "en": " and {n} more"}


@shared_task(queue="default", name="ordering.review_requests")
def review_requests() -> int:
    """Daily: "how was it?" a few days after a customer got their goods -- one message per purchase (review_requests.py)."""
    from apps.notifications.infrastructure.notify import notify
    from apps.ordering.infrastructure.review_requests import due
    from apps.products.infrastructure.models import ProductTranslation

    asks = due()
    names: dict = {}
    slugs: dict = {}
    for pid, locale, name, slug in ProductTranslation.objects.filter(product_id__in={p for a in asks for p in a.product_ids}).values_list("product_id", "locale_code", "name", "slug"):
        names.setdefault(pid, {})[locale] = name
        if slug and (locale == "uz" or pid not in slugs):
            slugs[pid] = slug
    sent = 0
    for ask in asks:
        first = ask.product_ids[0]
        product_names = names.get(first) or {}
        fallback = product_names.get("uz") or next(iter(product_names.values()), "")
        extra = len(ask.product_ids) - 1
        i18n = {lang: {"product": product_names.get(lang) or fallback, "more": more.format(n=extra) if extra else ""} for lang, more in _MORE_TEXT.items()}
        notify(ask.customer_id, "review_request", {"product": fallback, "more": i18n["uz"]["more"], "i18n": i18n},
               link=f"/products/{slugs[first]}#reviews" if first in slugs else "/orders", dedupe_key=f"review_request:{ask.ref}")
        sent += 1
    return sent
