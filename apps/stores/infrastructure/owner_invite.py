"""
A branch gets an owner (or a new one) → the owner is invited to NutriZoneAnalyticsBot: an inbox + Telegram
notification with a button straight into the bot (t.me/<bot>?start=owner). There, /start sends their own
branch's report at once, and every evening the daily report for their branches only (analytics_bot.audience).
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save, pre_save

logger = logging.getLogger("nutrizone.app")


def analytics_bot_link() -> str:
    from django.conf import settings

    name = (getattr(settings, "TELEGRAM_ANALYTICS_BOT_USERNAME", None) or "").lstrip("@")
    return f"https://t.me/{name}?start=owner" if name and getattr(settings, "TELEGRAM_ANALYTICS_BOT_TOKEN", None) else ""


def _remember_owner(sender, instance, **kwargs) -> None:
    if instance.pk:
        instance._nz_old_owner = sender.objects.filter(pk=instance.pk).values_list("owner_id", flat=True).first()
    else:
        instance._nz_old_owner = None


def _invite_new_owner(sender, instance, created, **kwargs) -> None:
    if kwargs.get("raw") or instance.kind != "store" or not instance.owner_id:
        return
    if not created and getattr(instance, "_nz_old_owner", None) == instance.owner_id:
        return
    link = analytics_bot_link()
    if not link:
        return
    from apps.notifications.infrastructure.notify import notify

    notify(instance.owner_id, "store_owner_analytics", {"store": instance.name}, link=link, dedupe_key=f"owner-invite:{instance.pk}:{instance.owner_id}")


def install() -> None:
    from apps.stores.infrastructure.models import Store

    pre_save.connect(_remember_owner, sender=Store, dispatch_uid="nz_store_owner_remember")
    post_save.connect(_invite_new_owner, sender=Store, dispatch_uid="nz_store_owner_invite")
