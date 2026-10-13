"""
POS Celery tasks -- orchestration only, never business logic.

**Only 1 task exists this phase: `relay_outbox_events`** -- the
standard, platform-wide, already-established Outbox relay mechanism
every certified module uses, not a POS-specific invention.

**Deliberately, no "flag stale open sales" visibility task exists**,
even though every prior module in this build has included an
analogous read-only, metric-only sweep (Chat's `flag_stale_
conversations`, Notifications' `flag_undelivered_notifications`,
Analytics' `flag_stale_draft_snapshots`). This phase's own brief
explicitly names "stale sale cleanup" among the forbidden speculative
capabilities (Section 21); even a strictly read-only, never-mutating
version risks being mistaken for exactly that. Absent stronger
evidence that this specific visibility need is required for POS, the
narrower, more literal reading of this phase's own explicit
prohibition is followed here.
"""
from __future__ import annotations

from celery import shared_task

from apps.pos.infrastructure import models as orm
from apps.pos.infrastructure.event_handlers import handle_pos_event
from core.outbox import OutboxRelay


@shared_task(queue="transactional", name="pos.relay_outbox_events")
def relay_outbox_events() -> dict:
    """Celery Beat-scheduled Outbox relay for the `pos` schema -- matches every prior module's identical relay task."""

    def _publish(event) -> bool:
        try:
            handle_pos_event(event.event_type, event.payload)
            return True
        except Exception:  # noqa: BLE001
            return False

    relay = OutboxRelay(orm.PosOutboxEvent, max_attempts=5, batch_size=100)
    return relay.relay_pending(publish_fn=_publish)
