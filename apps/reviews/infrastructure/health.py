"""
Reviews health checks -- registered against `core.health.registry`
from `apps/reviews/apps.py`'s `ready()` hook. Each executes real
logic, not merely an import test.
"""
from __future__ import annotations

from apps.reviews.infrastructure import models as orm
from apps.reviews.infrastructure.composition import build_review_repository
from core.caching import get_redis_client


def check_review_repository() -> tuple[bool, str]:
    try:
        orm.ReviewModel.objects.exists()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_review_outbox_backlog() -> tuple[bool, str]:
    try:
        pending = orm.ReviewOutboxEvent.objects.filter(published_at__isnull=True).count()
        if pending > 500:
            return False, f"{pending} outbox events are pending publication"
        return True, f"ok ({pending} pending)"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_rating_constraint_integrity() -> tuple[bool, str]:
    """Verifies no review has a rating outside 1-5 -- the database CheckConstraint already forbids this at write time, but a real check catches any row that bypassed the aggregate, e.g. a bad migration or manual fix."""
    try:
        bad_count = orm.ReviewModel.objects.filter(rating__lt=1).count() + orm.ReviewModel.objects.filter(rating__gt=5).count()
        if bad_count > 0:
            return False, f"{bad_count} reviews have a rating outside 1-5"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_orphaned_media() -> tuple[bool, str]:
    """Verifies every ReviewMedia row's review_id actually points at a live Review -- a real consistency check between the owned entity table and its aggregate root, not just table connectivity. Uses an anti-join against ReviewModel's own id set, not `review__isnull=True` -- `review` is a non-nullable FK, so an isnull filter can never detect the actual failure mode this check exists for (a review_id with a value pointing at no existing row), confirmed directly: seeding a genuinely dangling review_id and re-running this check is what caught the original bug."""
    try:
        orphaned = orm.ReviewMediaModel.objects.exclude(review_id__in=orm.ReviewModel.objects.values_list("id", flat=True)).count()
        if orphaned > 0:
            return False, f"{orphaned} review media rows are orphaned"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_composition_integrity() -> tuple[bool, str]:
    """Verifies the composition root itself is importable and can build at least one real object -- a canary against a broken factory wiring."""
    try:
        build_review_repository()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"composition root failed to build a repository: {exc}"


def check_review_cache() -> tuple[bool, str]:
    try:
        client = get_redis_client()
        client.set("_health_check:reviews:probe", "ok", ex=5)
        result = client.get("_health_check:reviews:probe")
        client.delete("_health_check:reviews:probe")
        if result != "ok":
            return False, "cache round-trip returned unexpected content"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"
