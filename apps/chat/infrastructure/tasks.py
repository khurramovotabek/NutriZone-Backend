"""
Chat Celery tasks -- orchestration only, never business logic.

**A disclosed limitation, matching the identical precedent already
established in Loyalty's and Reviews' own Phase 2**: no task here
mutates a `Conversation` or `Message` (e.g. "auto-close stale
conversations"). Every prior module's mutating tasks call a real
Application Service via `composition.py`; zero Application Services
exist for Chat, so no such service exists to call. A task that
constructed and mutated either aggregate directly here would be
exactly the "business logic in Infrastructure" violation this build
has treated as a real mistake elsewhere. `flag_stale_conversations`
below is genuinely real and useful without needing a mutating
service: it only reads and reports.
"""
from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone as django_timezone

from apps.chat.infrastructure import models as orm
from apps.chat.infrastructure.event_handlers import handle_chat_event, invalidate_chat_cache_group
from core.metrics import default_collector
from core.outbox import OutboxRelay

DEFAULT_STALE_THRESHOLD = timedelta(days=7)


@shared_task(queue="scheduled", name="chat.flag_stale_conversations")
def flag_stale_conversations() -> int:
    """Read-only visibility sweep -- reports (via metric) how many OPEN conversations have had no activity for longer than the stale threshold. Never mutates a Conversation; a future Application Service could act on this count once one exists."""
    cutoff = django_timezone.now() - DEFAULT_STALE_THRESHOLD
    stale_count = orm.ConversationModel.objects.filter(status="open", last_activity_at__lte=cutoff).count()
    default_collector.counter("chat_stale_conversations_count", stale_count)
    return stale_count


@shared_task(queue="scheduled", name="chat.rebuild_statistics")
def rebuild_chat_statistics() -> str:
    invalidate_chat_cache_group("conversation_list")
    return "ok"


@shared_task(queue="transactional", name="chat.relay_outbox_events")
def relay_outbox_events() -> dict:
    """Celery Beat-scheduled Outbox relay for the `chat` schema -- matches every prior module's identical relay task."""

    def _publish(event) -> bool:
        try:
            handle_chat_event(event.event_type, event.payload)
            return True
        except Exception:  # noqa: BLE001
            return False

    relay = OutboxRelay(orm.ChatOutboxEvent, max_attempts=5, batch_size=100)
    return relay.relay_pending(publish_fn=_publish)


@shared_task(queue="default", name="chat.alert_waiting")
def alert_waiting() -> dict:
    """Every 2 minutes (beat, migration 0006): unanswered support chats → the staff Telegram channel (automation.alert_waiting)."""
    from apps.chat.infrastructure.automation import alert_waiting as run

    return run()
