"""
Notifications read-model selectors -- optimized, read-only Postgres
queries. No business logic, no aggregate construction, matching the
pattern established by every prior module.
"""
from __future__ import annotations

import uuid

from django.db.models import Count

from apps.notifications.infrastructure import models as orm


class NotificationSelector:
    def list_for_recipient(self, recipient_id: uuid.UUID, status: str | None, page: int, page_size: int) -> tuple[list[dict], int]:
        qs = orm.NotificationModel.objects.filter(recipient_id=recipient_id)
        if status:
            qs = qs.filter(status=status)
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.order_by("-created_at")[start : start + page_size]
        return [self._card(r) for r in rows], total

    def _card(self, row: orm.NotificationModel) -> dict:
        return {"id": str(row.id), "notification_type": row.notification_type, "priority": row.priority, "title": row.title, "status": row.status, "created_at": row.created_at.isoformat()}


class NotificationStatisticsSelector:
    def counts_by_status(self, recipient_id: uuid.UUID | None = None) -> dict:
        """`recipient_id` is optional -- when supplied, scopes counts to one recipient's own notifications (a genuinely useful 'my unread count'-adjacent query); when omitted, returns platform-wide counts, matching every other module's own admin-facing statistics selector shape."""
        qs = orm.NotificationModel.objects.all()
        if recipient_id is not None:
            qs = qs.filter(recipient_id=recipient_id)
        rows = qs.values("status").annotate(count=Count("id"))
        return {r["status"]: r["count"] for r in rows}
