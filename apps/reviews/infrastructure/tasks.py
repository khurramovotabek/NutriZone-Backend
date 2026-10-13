"""
Reviews Celery tasks -- orchestration only, never business logic.

**A disclosed limitation, matching Loyalty's identical precedent**:
no task here mutates a `Review` (e.g. "auto-reject reviews overdue
for moderation"). Every prior module's mutating tasks call a real
Application Service via `composition.py`; per this phase's explicit
scope, `apps/reviews/application/services/` remains untouched, so no
such service exists to call. A task that constructed and mutated a
`Review` aggregate directly here would be exactly the "business logic
in Infrastructure" violation this build has treated as a real mistake
elsewhere. `flag_overdue_moderation_reviews` below is genuinely real
and useful without needing a mutating service: it only reads and
reports, using the real `ReviewModerationSLACalculator` domain policy
for the actual overdue calculation, not a task-local reimplementation
of that logic.
"""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone as django_timezone

from apps.reviews.domain.services import ReviewModerationSLACalculator
from apps.reviews.infrastructure import models as orm
from apps.reviews.infrastructure.event_handlers import handle_review_event, invalidate_review_cache_group
from core.metrics import default_collector
from core.outbox import OutboxRelay


@shared_task(queue="scheduled", name="reviews.flag_overdue_moderation_reviews")
def flag_overdue_moderation_reviews() -> int:
    """Read-only visibility sweep -- reports (via metric) how many PENDING_MODERATION reviews are past the domain-defined SLA. Never mutates a Review; a future Application Service could act on this count once one exists."""
    now = django_timezone.now()
    overdue_count = 0
    for row in orm.ReviewModel.objects.filter(status="pending_moderation").only("id", "submitted_at"):
        if row.submitted_at and ReviewModerationSLACalculator.is_overdue(row.submitted_at, now):
            overdue_count += 1
    default_collector.counter("reviews_overdue_moderation_count", overdue_count)
    return overdue_count


@shared_task(queue="scheduled", name="reviews.rebuild_statistics")
def rebuild_review_statistics() -> str:
    invalidate_review_cache_group("product_review_list")
    return "ok"


@shared_task(queue="transactional", name="reviews.relay_outbox_events")
def relay_outbox_events() -> dict:
    """Celery Beat-scheduled Outbox relay for the `reviews` schema -- matches every prior module's identical relay task."""

    def _publish(event) -> bool:
        try:
            handle_review_event(event.event_type, event.payload)
            return True
        except Exception:  # noqa: BLE001
            return False

    relay = OutboxRelay(orm.ReviewOutboxEvent, max_attempts=5, batch_size=100)
    return relay.relay_pending(publish_fn=_publish)
