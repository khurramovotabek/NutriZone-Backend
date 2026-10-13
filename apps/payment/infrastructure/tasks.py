"""Payment Celery tasks -- orchestration only (rules live in automation.py / reconcile.py)."""
from __future__ import annotations

from celery import shared_task


@shared_task(queue="default", name="payment.unpaid_orders")
def unpaid_orders() -> dict:
    """Every few minutes: remind customers who started an online payment, cancel the ones past the deadline."""
    from apps.payment.infrastructure import automation

    return {"reminded": automation.send_reminders(), "cancelled": automation.cancel_expired()}


@shared_task(queue="default", name="payment.reconcile")
def reconcile() -> dict:
    """Daily: payments vs orders vs providers (Dashboard → To'lovlar → Solishtirish)."""
    from apps.payment.infrastructure import reconcile as reconciliation
    from apps.payment.infrastructure.models import PaymentSettings

    if not PaymentSettings.load().reconcile_enabled:
        return {"skipped": True}
    return reconciliation.run()
