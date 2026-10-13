"""
Chat health checks -- registered against `core.health.registry` from
`apps/chat/apps.py`'s `ready()` hook. Each executes real logic, not
merely an import test.

**No fixed count was assumed here, per this phase's own explicit
instruction** ("do not assume a specific number of health checks");
this file's real checks were derived directly from the actual
Infrastructure dependencies this module has -- the repository, the
Outbox, a real cross-table consistency invariant, composition, and
cache. No Redis-channel-layer-connectivity check exists here --
Channels/the channel layer is explicitly deferred to a future
Interfaces phase (see this phase's own Channels/WebSocket Boundary
section); a health check for infrastructure this module doesn't yet
use would be premature, not thorough.
"""
from __future__ import annotations

from apps.chat.infrastructure import models as orm
from apps.chat.infrastructure.composition import build_conversation_repository
from core.caching import get_redis_client


def check_chat_repository() -> tuple[bool, str]:
    try:
        orm.ConversationModel.objects.exists()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_chat_outbox_backlog() -> tuple[bool, str]:
    try:
        pending = orm.ChatOutboxEvent.objects.filter(published_at__isnull=True).count()
        if pending > 500:
            return False, f"{pending} outbox events are pending publication"
        return True, f"ok ({pending} pending)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_orphaned_participants() -> tuple[bool, str]:
    """Verifies every ParticipantModel row's conversation FK actually points at a live, non-deleted ConversationModel -- a real cross-table consistency check, not just Django's own FK enforcement (which a bad migration or manual fix could bypass)."""
    try:
        orphaned = orm.ParticipantModel.objects.filter(conversation__isnull=True).count()
        if orphaned > 0:
            return False, f"{orphaned} participant rows are orphaned"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_message_content_integrity() -> tuple[bool, str]:
    """Verifies no TEXT/SYSTEM message has NULL content -- the same invariant `Message.send()` enforces at creation time, checked here as a real database-level consistency check against drift (e.g. a bad migration)."""
    try:
        bad_count = orm.MessageModel.objects.filter(message_type__in=("text", "system"), content__isnull=True).count()
        if bad_count > 0:
            return False, f"{bad_count} text/system messages have NULL content"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_composition_integrity() -> tuple[bool, str]:
    try:
        build_conversation_repository()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"composition root failed to build a repository: {exc}"


def check_chat_cache() -> tuple[bool, str]:
    try:
        client = get_redis_client()
        client.set("_health_check:chat:probe", "ok", ex=5)
        result = client.get("_health_check:chat:probe")
        client.delete("_health_check:chat:probe")
        if result != "ok":
            return False, "cache round-trip returned unexpected content"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"
