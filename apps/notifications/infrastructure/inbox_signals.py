"""
Business events → customer inbox (see notify.py). Hooked on ORM saves, like Loyalty's own reward signal, because
statuses also change from dashboard paths that never stage domain events; `dedupe_key` makes every hook idempotent.

- Order status: confirmed / processing / shipped / delivered / cancelled / returned / payment failed.
- Promo code (pricing Coupon, type "coupon") becoming ACTIVE, and a Campaign / flash sale becoming ACTIVE:
  one in-app broadcast to every customer (Telegram only when the dashboard sends it explicitly -- no spam).
- A new customer account: a welcome note.
Loyalty (coins, tier, referral, expiry, manual grants) is wired inside Loyalty's own notification funnel.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger("nutrizone.app")

ORDER_KINDS = {
    "confirmed": "order_confirmed", "processing": "order_processing", "shipped": "order_shipped",
    "delivered": "order_delivered", "cancelled": "order_cancelled", "returned": "order_returned", "failed": "order_failed",
}


@receiver(post_save, sender="ordering.OrderModel", dispatch_uid="notifications.order_status")
def _order_status(sender, instance, **kwargs) -> None:
    kind = ORDER_KINDS.get(instance.status)
    if kind is None or instance.customer_id is None:
        return
    from apps.notifications.infrastructure.notify import notify

    ctx = {"order": instance.order_number}
    if getattr(instance, "fulfilment_method", "delivery") == "pickup" and instance.status in ("shipped", "delivered"):
        # a pickup order is never "on its way": it's ready at the branch, then picked up
        kind = {"shipped": "order_ready_pickup", "delivered": "order_picked_up"}[instance.status]
        from apps.stores.infrastructure.models import Store

        store = Store.objects.filter(pk=instance.fulfilment_store_id).first()
        where = ", ".join(x for x in ((store.address, store.district, store.landmark) if store else ()) if x)
        ctx.update(store=store.name if store else "", address=where + (f". {store.pickup_note}" if store and store.pickup_note else ""))
    notify(instance.customer_id, kind, ctx, link=f"/orders/{instance.order_number}", dedupe_key=f"order:{instance.id}:{instance.status}")


def _discount(obj) -> str:
    from apps.notifications.infrastructure.notify import fmt

    if obj.discount_percentage:
        return f"{obj.discount_percentage.normalize():f}%"
    if obj.discount_fixed_amount:
        return f"{fmt(obj.discount_fixed_amount)} so'm"
    return ""


def _until(obj) -> dict:
    end = getattr(obj, "validity_ends_at", None)
    if not end:
        return {"uz": {"until": ""}, "ru": {"until": ""}, "en": {"until": ""}}
    from django.utils import timezone

    d = timezone.localtime(end).strftime("%d.%m.%Y")
    return {"uz": {"until": f", {d} gacha"}, "ru": {"until": f", до {d}"}, "en": {"until": f", until {d}"}}


def _announce(kind: str, obj, ctx: dict, link: str) -> None:
    from django.db import transaction

    from apps.notifications.infrastructure.models import NotificationBroadcast
    from apps.notifications.infrastructure.notify import render, start_broadcast

    if NotificationBroadcast.objects.filter(source=kind, source_ref=str(obj.pk)).exists():
        return  # each promo code / campaign is announced once, even if it's paused and re-activated
    texts = render(kind, {**ctx, "i18n": _until(obj)})
    with transaction.atomic():
        b = NotificationBroadcast.objects.create(
            kind=kind, title=texts["uz"]["title"], body=texts["uz"]["body"], i18n=texts, link=link, audience="all",
            send_in_app=True, send_telegram=False, source=kind, source_ref=str(obj.pk), created_by="auto",
        )
        start_broadcast(b)


def _remember_status(sender, instance, **kwargs) -> None:
    """Announce only the moment a promo/campaign *becomes* active -- editing one that is already live never re-broadcasts."""
    instance._nz_was_active = bool(instance.pk) and sender.objects.filter(pk=instance.pk, status="active").exists()


pre_save.connect(_remember_status, sender="pricing.CouponModel", dispatch_uid="notifications.coupon_prev_status")
pre_save.connect(_remember_status, sender="pricing.CampaignModel", dispatch_uid="notifications.campaign_prev_status")


def _just_activated(instance) -> bool:
    return instance.status == "active" and not getattr(instance, "_nz_was_active", False) and not getattr(instance, "is_deleted", False)


@receiver(post_save, sender="pricing.CouponModel", dispatch_uid="notifications.promo_code")
def _promo_code(sender, instance, **kwargs) -> None:
    if not _just_activated(instance) or instance.coupon_type != "coupon":
        return
    try:
        _announce("promo_code", instance, {"code": instance.code, "discount": _discount(instance)}, "/products")
    except Exception:  # noqa: BLE001
        logger.exception("notifications: promo announcement failed for %s", instance.pk)


@receiver(post_save, sender="pricing.CampaignModel", dispatch_uid="notifications.campaign")
def _campaign(sender, instance, **kwargs) -> None:
    if not _just_activated(instance):
        return
    try:
        _announce("campaign", instance, {"name": instance.name, "discount": _discount(instance)}, "/products")
    except Exception:  # noqa: BLE001
        logger.exception("notifications: campaign announcement failed for %s", instance.pk)


@receiver(post_save, sender="identity.User", dispatch_uid="notifications.welcome")
def _welcome(sender, instance, created: bool, **kwargs) -> None:
    if created:
        from apps.notifications.infrastructure.notify import notify

        notify(instance.pk, "welcome", link="/loyalty", dedupe_key=f"welcome:{instance.pk}", telegram=False)


# ---------------------------------------------------------------- returns & cancellations
# One notification per status (dedupe key), sent after commit from a fresh read: a status that was passed through
# inside the same transaction (approve + complete in one go) is skipped, and outcomes the order's own status already
# announces (order cancelled / returned) aren't announced twice.

def _after_sales_notify(model_label: str, pk, status: str) -> None:
    from django.apps import apps as django_apps

    from apps.notifications.infrastructure.notify import fmt, notify
    from apps.ordering.infrastructure.models import OrderModel

    row = django_apps.get_model(model_label).objects.filter(pk=pk).first()
    if row is None or row.status != status:
        return
    order = OrderModel.objects.filter(id=row.order_id).only("customer_id", "order_number", "status").first()
    if order is None or order.customer_id is None:
        return
    is_return = model_label == "ordering.OrderReturnModel"
    if is_return:
        kind = {"requested": "return_requested", "approved": "return_approved", "rejected": "return_rejected",
                "received": "return_received", "refunded": "return_refunded"}.get(status)
        if kind == "return_received" and order.status == "returned":
            kind = None  # "order returned" already tells the customer
    else:
        kind = {"requested": "cancellation_requested", "approved": "cancellation_approved",
                "completed": "cancellation_completed", "rejected": "cancellation_rejected"}.get(status)
        if kind == "cancellation_completed" and order.status == "cancelled":
            kind = None  # the whole order was cancelled: "order cancelled" already tells the customer
    if kind is None:
        return
    ctx = {
        "order": order.order_number, "number": getattr(row, "return_number", "") or order.order_number,
        "reason": (row.rejection_reason or "").strip() or "—",
        "amount": fmt(row.refund_amount) if row.refund_amount is not None else "",
    }
    quiet = kind in ("return_requested", "cancellation_requested")  # the customer just did it on the site: inbox only
    notify(order.customer_id, kind, ctx, link=f"/orders/{order.order_number}", dedupe_key=f"{kind}:{pk}", telegram=not quiet)


def _after_sales_status(sender, instance, **kwargs) -> None:
    from django.db import transaction

    label = f"{sender._meta.app_label}.{sender.__name__}"
    pk, status = instance.pk, instance.status

    def _run():
        try:
            _after_sales_notify(label, pk, status)
        except Exception:  # noqa: BLE001 - a notification must never break the workflow step
            logger.exception("after-sales notification failed for %s %s", label, pk)

    transaction.on_commit(_run)


post_save.connect(_after_sales_status, sender="ordering.OrderReturnModel", dispatch_uid="notifications.return_status")
post_save.connect(_after_sales_status, sender="ordering.OrderCancellationModel", dispatch_uid="notifications.cancellation_status")
