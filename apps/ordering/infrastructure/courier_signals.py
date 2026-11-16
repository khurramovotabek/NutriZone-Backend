"""Links a pre-entered courier to the account created later with the same phone (see couriers.auto_link_account)."""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger("nutrizone.app")


@receiver(post_save, sender="identity.User", dispatch_uid="ordering.courier_auto_link")
def courier_auto_link(sender, instance, created, update_fields=None, **kwargs):
    if not created and update_fields is not None and "phone_number" not in update_fields:
        return
    try:
        from apps.ordering.infrastructure import couriers

        courier = couriers.auto_link_account(instance)
        if courier is not None:
            logger.info("courier %s linked to account %s by phone", courier.code, instance.pk)
    except Exception:  # noqa: BLE001 - signing up must never fail because of the courier link
        logger.exception("courier auto-link failed for user %s", getattr(instance, "pk", None))
