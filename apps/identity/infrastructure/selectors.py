"""
Phase 03B Dashboard completion: Identity had no statistics selector at
all -- this closes the "customer statistics" gap using only existing,
unambiguous domain fields. `UserStatus` (ACTIVE/BLOCKED/
PENDING_VERIFICATION) already has clear business meaning; no new
customer definition is invented here.
"""
from django.db.models import Count

from apps.identity.infrastructure import models as orm


class UserStatisticsSelector:
    def counts_by_status(self) -> dict[str, int]:
        rows = orm.User.objects.values("status").annotate(count=Count("id"))
        return {r["status"]: r["count"] for r in rows}

    def total_customers(self) -> int:
        return orm.User.objects.count()
