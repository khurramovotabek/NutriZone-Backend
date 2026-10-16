"""Records PaymentEvent rows on every PaymentModel status change (signals) -- plus `record()` for bulk updates."""
from __future__ import annotations

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.payment.infrastructure.models import PaymentEvent, PaymentModel


def record(payment: PaymentModel, from_status: str, to_status: str, note: str = "") -> None:
    PaymentEvent.objects.create(payment=payment, from_status=from_status or "", to_status=to_status, provider=payment.provider,
                                provider_state=payment.provider_state, amount=payment.amount, note=(note or payment.failure_reason or "")[:255])


@receiver(pre_save, sender=PaymentModel, dispatch_uid="payment_history_pre")
def _remember(sender, instance, **kwargs):
    instance._old_status = PaymentModel.objects.filter(pk=instance.pk).values_list("status", flat=True).first() if not instance._state.adding else None


@receiver(post_save, sender=PaymentModel, dispatch_uid="payment_history_post")
def _record(sender, instance, created, **kwargs):
    old = getattr(instance, "_old_status", None)
    if created or old != instance.status:
        record(instance, "" if created else old, instance.status, "to'lov urinishi yaratildi" if created else "")
