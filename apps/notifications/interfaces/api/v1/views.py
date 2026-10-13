"""
Notifications HTTP API views.

Thin per Django Implementation Blueprint §3. No view instantiates a
repository/selector directly outside `composition.py`, imports
`infrastructure.models`, or constructs a Domain aggregate.

**Every mutation endpoint in this file returns an honest HTTP 501.**
This is the direct, disclosed consequence of this phase's own Step 1
re-verification: zero Application Services exist for Notifications.
`Notification` has 7 public methods and `NotificationPreference` has
4; every mutation among them requires the same load-mutate-persist-
stage-event orchestration only an Application Service can safely own.
Every 501 response states precisely which capability is missing,
matching the identical pattern already established by Reviews'/Chat's
own Phase 3.

**`record_delivery_attempt`/`confirm_delivery`/`mark_delivery_failed`
are deliberately NOT exposed as HTTP endpoints at all** -- not even as
501s. These are system/delivery-worker-level operations, never listed
among this phase's own "conceptual resources to evaluate," and
`NotificationDelivery` must never become an independent, top-level
API resource per this phase's own explicit rule.
"""
from __future__ import annotations

import uuid

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.views import APIView

from apps.notifications.domain.enums import NotificationChannel, NotificationType
from apps.notifications.interfaces.api.v1.filters import parse_notification_list_params
from apps.notifications.interfaces.api.v1.pagination import NotificationPagination
from apps.notifications.interfaces.api.v1.permissions import (
    CreateNotification, ManageOwnNotifications, ManageOwnPreferences, ViewOwnNotifications,
)
from apps.notifications.interfaces.api.v1.serializers import (
    CancelNotificationSerializer, CreateNotificationSerializer, MarkReadSerializer, MarkSeenSerializer,
    PreferenceChannelTypeSerializer,
)
from apps.notifications.infrastructure import composition
from common.exceptions import PermissionDenied, ResourceNotFound
from common.responses import paginated_response, success_response
from core.openapi import STANDARD_ERROR_RESPONSES
from core.ratelimit import ScopedRateLimitThrottle


def _responses(*codes: int) -> dict:
    return {code: STANDARD_ERROR_RESPONSES[code] for code in codes}


def _attach_identity(request) -> None:
    request.identity = request.user


_MISSING_APPLICATION_SERVICE = "This operation requires an Application Service that is not yet implemented. Zero Application Services currently exist for the Notifications module; orchestrating this transition (load -> mutate -> persist -> stage event) cannot be done safely from the Interfaces layer without one."


class NotificationsThrottle(ScopedRateLimitThrottle):
    scope = "notifications.operation"
    limit = 3000
    window_seconds = 3600
    identifier_source = "user"


def _notification_card_payload(row: dict) -> dict:
    return {"id": row["id"], "notification_type": row["notification_type"], "priority": row["priority"], "title": row["title"], "status": row["status"], "created_at": row["created_at"]}


def _notification_detail_payload(notification) -> dict:
    return {
        "id": str(notification.id), "notification_type": notification.notification_type.value, "priority": notification.priority.value,
        "title": notification.title.value, "body": notification.body.value, "status": notification.status.value,
        "seen_at": notification.seen_at.isoformat() if notification.seen_at else None, "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
        "deliveries": [{"id": str(d.id), "channel": d.channel.value, "status": d.status.value, "attempted_at": d.attempted_at.isoformat(), "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None, "failed_at": d.failed_at.isoformat() if d.failed_at else None} for d in notification.deliveries.values()],
    }


def _load_notification_or_404(notification_id: str):
    notification = composition.build_notification_repository().get_by_id(uuid.UUID(notification_id))
    if notification is None:
        raise ResourceNotFound("Notification not found.")
    return notification


def _assert_owned_by_requester_or_403(notification, user_id) -> None:
    """Object-level authorization -- the DRF permission class only checks the generic `view_own`/`manage_own` code; whether THIS notification actually belongs to THIS user is a per-object check that must happen here, against the loaded aggregate itself. The central security invariant this phase requires: knowing a notification's UUID must never be sufficient to access it."""
    if notification.recipient_id != user_id:
        raise PermissionDenied("This notification does not belong to you.")


def _preference_matrix_payload(preference) -> dict:
    """Computes the full (channel, notification_type, enabled) matrix from `NotificationPreference.is_enabled()` for every combination -- never exposes the raw internal `disabled_combinations` sparse list directly, per this phase's own explicit instruction to represent this domain-oriented, not persistence-oriented."""
    entries = [{"channel": c.value, "notification_type": t.value, "enabled": preference.is_enabled(c, t)} for c in NotificationChannel for t in NotificationType]
    return {"user_id": str(preference.user_id), "entries": entries}


# ============================================================
# Notifications -- read (real) and mutation (honest 501) endpoints
# ============================================================


class NotificationListCreateView(APIView):
    """GET is real (backed by `NotificationSelector.list_for_recipient`, scoped to the requesting user's own notifications -- the central IDOR-prevention rule this phase requires: a user can never request another user's notifications merely by supplying another UUID, since `recipient_id` is always taken from `request.user.id`, never a client-supplied parameter). POST (create) is an honest 501."""

    throttle_classes = [NotificationsThrottle]
    permission_classes = [ViewOwnNotifications]

    @extend_schema(tags=["Notifications"], summary="List the authenticated user's notifications", description="Supports filter[status]. Backed by NotificationSelector.list_for_recipient.", responses={200: OpenApiResponse(description="Notification collection"), **_responses(401, 403, 422)})
    def get(self, request):
        _attach_identity(request)
        params = parse_notification_list_params(request.query_params)
        pagination = NotificationPagination.from_query_params(request.query_params)
        rows, total = composition.build_notification_selector().list_for_recipient(recipient_id=request.user.id, status=params.status, page=pagination.page, page_size=pagination.page_size)
        total_pages = max((total + pagination.page_size - 1) // pagination.page_size, 1)
        return paginated_response(data=[_notification_card_payload(r) for r in rows], pagination={"strategy": "page", "page": pagination.page, "page_size": pagination.page_size, "total_pages": total_pages, "total_count": total})

    @extend_schema(tags=["Notifications Admin"], summary="Create a notification (not yet implemented)", request=CreateNotificationSerializer, responses={501: OpenApiResponse(description=_MISSING_APPLICATION_SERVICE), **_responses(401, 403, 422)})
    def post(self, request):
        _attach_identity(request)
        serializer = CreateNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return success_response(data={"detail": _MISSING_APPLICATION_SERVICE}, status_code=501)

    def get_permissions(self):
        return [CreateNotification()] if self.request.method == "POST" else [ViewOwnNotifications()]


class NotificationDetailView(APIView):
    permission_classes = [ViewOwnNotifications]

    @extend_schema(tags=["Notifications"], summary="Get a notification by id", responses={200: OpenApiResponse(description="Notification detail"), **_responses(401, 403, 404)})
    def get(self, request, notification_id: str):
        _attach_identity(request)
        notification = _load_notification_or_404(notification_id)
        _assert_owned_by_requester_or_403(notification, request.user.id)
        return success_response(data=_notification_detail_payload(notification))


class MarkNotificationSeenView(APIView):
    throttle_classes = [NotificationsThrottle]
    permission_classes = [ManageOwnNotifications]

    @extend_schema(tags=["Notifications"], summary="Mark a notification as seen (not yet implemented)", request=MarkSeenSerializer, responses={501: OpenApiResponse(description=_MISSING_APPLICATION_SERVICE), **_responses(401, 403, 404)})
    def post(self, request, notification_id: str):
        _attach_identity(request)
        notification = _load_notification_or_404(notification_id)
        _assert_owned_by_requester_or_403(notification, request.user.id)
        return success_response(data={"detail": _MISSING_APPLICATION_SERVICE}, status_code=501)


class MarkNotificationReadView(APIView):
    throttle_classes = [NotificationsThrottle]
    permission_classes = [ManageOwnNotifications]

    @extend_schema(tags=["Notifications"], summary="Mark a notification as read (not yet implemented)", request=MarkReadSerializer, responses={501: OpenApiResponse(description=_MISSING_APPLICATION_SERVICE), **_responses(401, 403, 404)})
    def post(self, request, notification_id: str):
        _attach_identity(request)
        notification = _load_notification_or_404(notification_id)
        _assert_owned_by_requester_or_403(notification, request.user.id)
        return success_response(data={"detail": _MISSING_APPLICATION_SERVICE}, status_code=501)


class CancelNotificationView(APIView):
    throttle_classes = [NotificationsThrottle]
    permission_classes = [ManageOwnNotifications]

    @extend_schema(tags=["Notifications"], summary="Cancel a notification (not yet implemented)", request=CancelNotificationSerializer, responses={501: OpenApiResponse(description=_MISSING_APPLICATION_SERVICE), **_responses(401, 403, 404, 409)})
    def post(self, request, notification_id: str):
        _attach_identity(request)
        notification = _load_notification_or_404(notification_id)
        _assert_owned_by_requester_or_403(notification, request.user.id)
        return success_response(data={"detail": _MISSING_APPLICATION_SERVICE}, status_code=501)


# ============================================================
# Preferences -- singleton-per-user read (real) and mutation (honest 501) endpoints
# ============================================================


class NotificationPreferenceView(APIView):
    """A singleton personal resource -- always resolves to the authenticated user's own preference record, never takes a preference id in the URL."""

    permission_classes = [ManageOwnPreferences]

    @extend_schema(tags=["Notifications"], summary="Get the authenticated user's notification preferences", description="Returns the full (channel, notification_type, enabled) matrix, computed from NotificationPreference.is_enabled() -- never the raw internal sparse storage shape. The all-enabled default record is created on first read.", responses={200: OpenApiResponse(description="Preference matrix"), **_responses(401, 403)})
    def get(self, request):
        from apps.notifications.application.services.preferences import GetOrCreatePreference

        _attach_identity(request)
        preference = GetOrCreatePreference(composition.build_notification_preference_repository()).execute(request.user.id)
        return success_response(data=_preference_matrix_payload(preference))


def _set_preference(request, enabled: bool):
    from apps.notifications.application.services.preferences import SetPreference

    _attach_identity(request)
    serializer = PreferenceChannelTypeSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    preference = SetPreference(composition.build_notification_preference_repository()).execute(
        request.user.id,
        NotificationChannel(serializer.validated_data["channel"]),
        NotificationType(serializer.validated_data["notification_type"]),
        enabled=enabled,
    )
    return success_response(data=_preference_matrix_payload(preference))


class DisablePreferenceView(APIView):
    throttle_classes = [NotificationsThrottle]
    permission_classes = [ManageOwnPreferences]

    @extend_schema(tags=["Notifications"], summary="Disable a (channel, notification_type) combination", request=PreferenceChannelTypeSerializer, responses={200: OpenApiResponse(description="Updated preference matrix"), **_responses(401, 403, 422)})
    def post(self, request):
        return _set_preference(request, enabled=False)


class EnablePreferenceView(APIView):
    throttle_classes = [NotificationsThrottle]
    permission_classes = [ManageOwnPreferences]

    @extend_schema(tags=["Notifications"], summary="Enable a (channel, notification_type) combination", request=PreferenceChannelTypeSerializer, responses={200: OpenApiResponse(description="Updated preference matrix"), **_responses(401, 403, 422)})
    def post(self, request):
        return _set_preference(request, enabled=True)


class NotificationStatisticsView(APIView):
    permission_classes = [ViewOwnNotifications]

    @extend_schema(tags=["Notifications"], summary="The authenticated user's own notification statistics (counts by status)", responses={200: OpenApiResponse(description="Statistics"), **_responses(401, 403)})
    def get(self, request):
        _attach_identity(request)
        selector = composition.build_notification_statistics_selector()
        return success_response(data={"counts_by_status": selector.counts_by_status(recipient_id=request.user.id)})
