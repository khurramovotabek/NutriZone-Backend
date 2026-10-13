"""
Identity Celery tasks -- thin wrappers around Application Services or
simple scheduled housekeeping (Django Implementation Blueprint §3/§8).
No business logic lives here beyond the housekeeping itself, which is
infrastructure-level (purging expired ephemeral rows), not a business
rule.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.identity.infrastructure import models as orm
from core.outbox import OutboxRelay


@shared_task(queue="scheduled", name="identity.purge_expired_otp_codes")
def purge_expired_otp_codes() -> int:
    """Hard-deletes OTP challenges 24h past expiry (Database Blueprint §13's retention table for `otp_codes`)."""
    cutoff = timezone.now() - timezone.timedelta(hours=24)
    deleted, _ = orm.OTPCodeChallenge.objects.filter(expires_at__lt=cutoff).delete()
    return deleted


@shared_task(queue="scheduled", name="identity.purge_expired_sessions")
def purge_expired_sessions() -> int:
    """Hard-deletes sessions 30 days past expiry (Database Blueprint §13's retention table for `user_sessions`)."""
    cutoff = timezone.now() - timezone.timedelta(days=30)
    deleted, _ = orm.UserSession.objects.filter(expires_at__lt=cutoff).delete()
    return deleted


@shared_task(queue="transactional", name="identity.relay_outbox_events")
def relay_outbox_events() -> dict:
    """
    Celery Beat-scheduled relay for the `identity` schema's Outbox
    (Django Implementation Blueprint §8, core/outbox/publisher.py's
    OutboxRelay). The actual publish mechanism (dispatching to
    Notifications/Analytics/Audit consumers) is deferred until those
    consuming modules exist; for now this relay marks events published
    against a no-op sink so the retry/dead-letter mechanics are
    exercised end-to-end without a real downstream consumer yet.
    """
    relay = OutboxRelay(orm.IdentityOutboxEvent, max_attempts=5, batch_size=100)
    return relay.relay_pending(publish_fn=lambda event: True)
