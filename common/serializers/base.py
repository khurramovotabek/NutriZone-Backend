"""
Base serializer mixins and the base viewset every module's API views
inherit from (Django Implementation Blueprint §5).

Only base MIXINS live here -- no business serializers. Each app's
`interfaces/api/v1/serializers.py` subclasses these.
"""
from __future__ import annotations

from typing import Any

from rest_framework import serializers, viewsets
from rest_framework.response import Response

from common.responses.envelope import paginated_response, success_response


class ReadOnlyAuditFieldsMixin(serializers.Serializer):
    """
    Every serializer exposing a BaseModel-derived model includes these
    read-only, per the Database Blueprint §3 Global Base Entity Standard.
    """

    id = serializers.UUIDField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    version = serializers.IntegerField(read_only=True)


class AppendOnlyAuditFieldsMixin(serializers.Serializer):
    """For AppendOnlyModel-derived resources (Ledger/History/Audit/Snapshot)."""

    id = serializers.UUIDField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class EnvelopeModelViewSet(viewsets.GenericViewSet):
    """
    Base viewset that renders every response through the standard
    envelope (common/responses/envelope.py) and the standard pagination
    meta shape -- a concrete app viewset composes DRF mixins
    (ListModelMixin, CreateModelMixin, ...) alongside this base rather
    than DRF's own ModelViewSet, so the envelope wiring is never
    bypassed.

    Business modules are expected to override `perform_list_query`,
    `perform_retrieve`, etc. by calling their own module's
    `application/selectors.py` / `application/services/` -- this base
    class contains no ORM access itself.
    """

    def get_paginated_envelope(self, data: list[Any]) -> Response:
        paginator = self.paginator
        meta = paginator.get_paginated_meta() if paginator and hasattr(paginator, "get_paginated_meta") else {}
        return paginated_response(data=data, pagination=meta)

    def get_success_envelope(self, data: Any, status_code: int = 200) -> Response:
        return success_response(data=data, status_code=status_code)
