"""Loyalty Celery tasks -- orchestration only; the decisions live in services.py."""
from __future__ import annotations

from datetime import timedelta

from celery import shared_task


@shared_task(queue="default", name="loyalty.reconcile_order_rewards")
def reconcile_order_rewards() -> dict:
    """Awards/reverses/refunds any order whose coin state is out of step with its status (idempotent)."""
    from apps.loyalty.infrastructure.services import reconcile

    return reconcile()


@shared_task(queue="default", name="loyalty.expire_coins")
def expire_coins() -> dict:
    """Burns expired lots, then sends one reminder per customer for coins expiring within the reminder window."""
    from django.db.models import Min, Sum
    from django.utils import timezone

    from apps.loyalty.infrastructure import notifications
    from apps.loyalty.infrastructure.models import LoyaltySettings, WalletTransaction
    from apps.loyalty.infrastructure.services import expire_lots

    expired = expire_lots()
    cfg = LoyaltySettings.load()
    reminded = 0
    if cfg.expiry_reminder_days:
        now = timezone.now()
        due = WalletTransaction.objects.filter(remaining__gt=0, expiry_notified_at__isnull=True, expires_at__gt=now, expires_at__lte=now + timedelta(days=cfg.expiry_reminder_days))
        for row in due.values("wallet__user_id").annotate(coins=Sum("remaining"), first=Min("expires_at")):
            notifications.queue("expiring", row["wallet__user_id"], coins=row["coins"], date=timezone.localtime(row["first"]).strftime("%d.%m.%Y"))
            reminded += 1
        due.update(expiry_notified_at=now)
    return {"expired_lots": expired, "reminded_customers": reminded}


TIER_RISK_REMIND_DAYS = 14


@shared_task(queue="default", name="loyalty.tier_risk_reminders")
def tier_risk_reminders() -> dict:
    """
    Daily: warns customers whose tier lapses within TIER_RISK_REMIND_DAYS (purchases leaving the rolling
    window) and tells them how much more to buy. Inbox + Telegram; the dedupe key sends each deadline once.
    """
    from django.db.models import Q
    from django.utils import timezone

    from apps.loyalty.infrastructure import notifications, services
    from apps.ordering.infrastructure.models import OrderModel
    from apps.pos.infrastructure.models import SaleModel

    days = services.programme().tier_window_days
    if days == 0:
        return {"checked": 0, "warned": 0}
    now = timezone.now()
    lo, hi = now - timedelta(days=days), now - timedelta(days=days) + timedelta(days=TIER_RISK_REMIND_DAYS)
    # Only customers with a purchase about to leave the window can lose a tier in time.
    ids = set(
        OrderModel.objects.filter(status__in=services.FULFILLED_STATUSES, customer_id__isnull=False)
        .filter(Q(placed_at__gte=lo, placed_at__lt=hi) | Q(placed_at__isnull=True, created_at__gte=lo, created_at__lt=hi))
        .values_list("customer_id", flat=True)
    ) | set(SaleModel.objects.filter(status="completed", customer_id__isnull=False, completed_at__gte=lo, completed_at__lt=hi).values_list("customer_id", flat=True))
    warned = 0
    for uid in ids:
        risk = services.tier_risk(uid, horizon_days=TIER_RISK_REMIND_DAYS, now=now)
        if risk is None:
            continue
        notifications.queue(
            "tier_risk", uid, tier=risk.tier.name, tier_slug=risk.tier.slug, lower=risk.falls_to.name if risk.falls_to else "—",
            needed=int(risk.needed), percent=f"{risk.tier.percent.normalize():f}", date=timezone.localtime(risk.drop_at).strftime("%d.%m.%Y"),
        )
        warned += 1
    return {"checked": len(ids), "warned": warned}


@shared_task(queue="default", name="loyalty.send_notification", autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def send_loyalty_notification(kind: str, user_id: str, payload: dict) -> bool:
    from apps.loyalty.infrastructure.notifications import send

    return send(kind, user_id, payload)
