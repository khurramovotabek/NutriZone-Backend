"""
Keeps coin rewards in step with order status the moment it changes.

Listens to Ordering's ORM `post_save` rather than its outbox events: in
practice order statuses are also changed from the admin/dashboard paths
that don't stage `OrderDelivered`/`OrderCompleted` events (confirmed:
delivered orders exist with no matching outbox row), while every path
does save the row. The work runs `on_commit`, so a rolled-back status
change never pays out, and any failure is swallowed here and picked up
by the periodic `loyalty.reconcile_order_rewards` task instead of
breaking the order save itself.
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.loyalty.infrastructure.services import FULFILLED_STATUSES, REVERSING_STATUSES, sync_order_and_notify
from apps.ordering.infrastructure.models import OrderModel

logger = logging.getLogger("nutrizone.app")


@receiver(post_save, sender=OrderModel, dispatch_uid="loyalty.sync_order_reward")
def _on_order_saved(sender, instance: OrderModel, **kwargs) -> None:
    if instance.customer_id is None or instance.status not in (*FULFILLED_STATUSES, *REVERSING_STATUSES):
        return
    order_id = instance.id

    def _run() -> None:
        try:
            sync_order_and_notify(order_id)
        except Exception:  # noqa: BLE001 - never break an order save; reconcile retries it
            logger.exception("loyalty: reward sync failed for order %s (reconcile will retry)", order_id)

    transaction.on_commit(_run)


@receiver(post_save, sender="identity.User", dispatch_uid="loyalty.wallet_for_new_user")
def _wallet_for_new_user(sender, instance, created: bool, **kwargs) -> None:
    """Every account gets its (empty) wallet at sign-up, so Loyalty Management lists every customer with their tier and coins."""
    if created:
        from apps.loyalty.infrastructure.models import Wallet

        Wallet.objects.get_or_create(user_id=instance.pk)
