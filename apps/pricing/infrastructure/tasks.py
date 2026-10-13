"""
Pricing Celery tasks -- orchestration only. Every task loads data,
calls a real Application Service or domain policy for the actual
decision, and persists/reports the result -- never business logic
itself.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone as django_timezone

from apps.pricing.infrastructure import models as orm
from apps.pricing.infrastructure.event_handlers import handle_pricing_event
from core.outbox import OutboxRelay


@shared_task(queue="scheduled", name="pricing.expire_campaigns")
def expire_campaigns() -> int:
    """Sweeps every ACTIVE campaign past its validity window and calls the real `EndCampaign` Application Service for each."""
    from apps.pricing.infrastructure.composition import build_end_campaign
    from apps.pricing.infrastructure.repositories import DjangoCampaignRepository

    now = django_timezone.now()
    rows = orm.CampaignModel.objects.filter(status="active", validity_ends_at__isnull=False, validity_ends_at__lte=now)
    repo = DjangoCampaignRepository()
    count = 0
    for row in rows:
        campaign = repo.get_by_id(row.id)
        if campaign is None:
            continue
        try:
            build_end_campaign().execute(campaign.id)
            count += 1
        except Exception:  # noqa: BLE001 - one failure must not abort the sweep for the rest
            continue
    return count


@shared_task(queue="scheduled", name="pricing.expire_price_snapshots")
def expire_price_snapshots() -> int:
    """Sweeps every LOCKED snapshot past its expiry -- calls the real domain aggregate method (loaded, mutated, saved) rather than setting `status` directly."""
    from apps.pricing.domain.enums import PriceSnapshotStatus
    from apps.pricing.infrastructure.repositories import DjangoPriceSnapshotRepository

    now = django_timezone.now()
    repo = DjangoPriceSnapshotRepository()
    rows = orm.PriceSnapshotModel.objects.filter(status="locked", expires_at__lte=now)
    count = 0
    for row in rows:
        snapshot = repo.get_by_id(row.id)
        if snapshot is None:
            continue
        snapshot.status = PriceSnapshotStatus.EXPIRED
        repo.save(snapshot)
        count += 1
    return count


@shared_task(queue="scheduled", name="pricing.expire_coupons")
def expire_coupons() -> int:
    """Sweeps every ACTIVE coupon past its validity window."""
    from apps.pricing.domain.enums import CouponStatus

    now = django_timezone.now()
    updated = orm.CouponModel.objects.filter(status=CouponStatus.ACTIVE.value, validity_ends_at__isnull=False, validity_ends_at__lte=now).update(status=CouponStatus.EXPIRED.value)
    return updated


@shared_task(queue="scheduled", name="pricing.activate_scheduled_campaigns")
def activate_scheduled_campaigns() -> int:
    """Sweeps every SCHEDULED campaign whose validity window has started and calls the real `ActivateCampaign` Application Service."""
    from apps.pricing.infrastructure.composition import build_activate_campaign

    now = django_timezone.now()
    rows = orm.CampaignModel.objects.filter(status="scheduled", validity_starts_at__lte=now)
    count = 0
    for row in rows:
        try:
            build_activate_campaign().execute(row.id)
            count += 1
        except Exception:  # noqa: BLE001
            continue
    return count


@shared_task(queue="scheduled", name="pricing.rebuild_statistics")
def rebuild_statistics() -> str:
    from apps.pricing.infrastructure.event_handlers import invalidate_pricing_cache_group

    invalidate_pricing_cache_group("campaigns")
    invalidate_pricing_cache_group("coupons")
    return "ok"


@shared_task(queue="transactional", name="pricing.relay_outbox_events")
def relay_outbox_events() -> dict:
    """Celery Beat-scheduled Outbox relay for the `pricing` schema -- matches every prior module's identical relay task."""

    def _publish(event) -> bool:
        try:
            handle_pricing_event(event.event_type, event.payload)
            return True
        except Exception:  # noqa: BLE001
            return False

    relay = OutboxRelay(orm.PricingOutboxEvent, max_attempts=5, batch_size=100)
    return relay.relay_pending(publish_fn=_publish)
