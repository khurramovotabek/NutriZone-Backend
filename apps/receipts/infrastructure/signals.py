"""Receipts appear by themselves: a POS sale when it completes, an online order when it is delivered / completed."""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger("nutrizone.receipts")


def _safe(fn, obj):
    def run():
        try:
            fn(obj)
        except Exception:  # noqa: BLE001 -- a receipt problem never breaks a sale or an order
            logger.exception("receipt for %s failed", obj.pk)
    transaction.on_commit(run)


@receiver(post_save, sender="pos.SaleModel", dispatch_uid="receipts_from_sale")
def sale_saved(sender, instance, **kwargs):
    if instance.status == "completed" and instance.receipt_number:
        from apps.receipts.infrastructure.builders import from_sale

        _safe(from_sale, instance)


@receiver(post_save, sender="ordering.OrderModel", dispatch_uid="receipts_from_order")
def order_saved(sender, instance, **kwargs):
    if instance.status in ("delivered", "completed"):
        from apps.receipts.infrastructure.builders import from_order

        _safe(from_order, instance)
