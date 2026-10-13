"""
Audit API views.

`GET /internal/audit/activity` -- REST API Blueprint §13, cursor-
paginated. Uses `common.pagination.pagination.StandardCursorPagination`
directly, standalone (not via `GenericAPIView.paginate_queryset()` --
every other view in this repository uses plain `APIView`, so this
keeps that established convention rather than switching base classes
for one endpoint). DRF's `CursorPagination.paginate_queryset()` is
documented to work this way outside `GenericAPIView`. This is the
first real caller of this pagination class anywhere in the repository
(confirmed by search before writing this file) -- reused, not
duplicated, per this phase's own evidence-driven mandate.
"""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.views import APIView

from apps.audit.infrastructure import composition
from apps.audit.interfaces.api.v1.permissions import ViewActivityTimeline
from apps.audit.interfaces.api.v1.serializers import ActivityTimelineEntrySerializer
from common.pagination.pagination import StandardCursorPagination
from common.responses import paginated_response
from core.openapi import STANDARD_ERROR_RESPONSES


def _responses(*codes: int) -> dict:
    return {code: STANDARD_ERROR_RESPONSES[code] for code in codes}


class ActivityTimelineListView(APIView):
    """`GET /internal/audit/activity` -- `audit.log.view` (or `identity.user.view`, per the blueprint's own text; this module defines its own dedicated code -- see permissions.py)."""

    permission_classes = [ViewActivityTimeline]

    @extend_schema(
        tags=["Audit"], summary="Cross-context activity timeline (cursor-paginated)",
        responses={200: ActivityTimelineEntrySerializer(many=True), **_responses(401, 403, 422)},
    )
    def get(self, request):
        entity_type = request.query_params.get("entity_type")
        entity_id = request.query_params.get("entity_id")
        queryset = composition.build_list_activity_timeline().execute(entity_type=entity_type, entity_id=entity_id)

        paginator = StandardCursorPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = ActivityTimelineEntrySerializer([_entry_payload(e) for e in page], many=True)
        return paginated_response(data=serializer.data, pagination=paginator.get_paginated_meta())


def _entry_payload(entry) -> dict:
    return {
        "id": entry.id, "actor_id": entry.actor_id, "action_type": entry.action_type,
        "entity_type": entry.entity_type, "entity_id": entry.entity_id, "context_schema": entry.context_schema,
        "before_snapshot": entry.before_snapshot, "after_snapshot": entry.after_snapshot,
        "occurred_at": entry.occurred_at, "created_at": entry.created_at,
    }
