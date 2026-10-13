"""
Full-stack HTTP API integration tests -- real URL routing,
serializers, views, and repository/selector layer together against a
real database.

**Every mutation endpoint tested here is expected to return HTTP
501, per this module's disclosed zero-Application-Service state.**
**The central IDOR-prevention invariant this phase requires is
verified end-to-end via real HTTP requests, not just by reading
`views.py`'s own source**: a notification belonging to User A must
never be accessible or mutable by an authenticated User B.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.notifications.infrastructure.repositories import DjangoNotificationPreferenceRepository, DjangoNotificationRepository
from apps.notifications.tests.factories import make_notification, make_preference
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


class _DenyAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return False


class TestUnauthenticatedAccess:
    def test_notification_list_requires_auth(self, api_client):
        response = api_client.get("/api/v1/notifications/")
        assert response.status_code == 401


class TestPermissionDenial:
    @pytest.fixture(autouse=True)
    def _authenticated_but_unauthorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _DenyAllResolver()
        fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    def test_notification_list_denied(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get("/api/v1/notifications/")
        assert response.status_code == 403


class TestAuthorizedFlows:
    @pytest.fixture(autouse=True)
    def _authenticated_and_authorized(self, monkeypatch):
        original = HasPermissionCode.resolver
        HasPermissionCode.resolver = _AllowAllResolver()
        self.fake_user_id = uuid.uuid4()
        fake_user = SimpleNamespace(id=self.fake_user_id, is_authenticated=True, store_ids=set())
        monkeypatch.setattr(
            "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
            lambda self, request: (fake_user, None),
        )
        yield
        HasPermissionCode.resolver = original

    # --- Working (read) endpoints, all 4 ---------------------------------

    def test_list_own_notifications(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        notification = make_notification(recipient_id=self.fake_user_id)
        DjangoNotificationRepository().save(notification)
        response = api_client.get("/api/v1/notifications/")
        assert response.status_code == 200
        assert "pagination" in response.json()

    def test_notification_list_excludes_other_users_notifications(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        make_notification()  # someone else's, not saved to self.fake_user_id
        DjangoNotificationRepository().save(make_notification())
        response = api_client.get("/api/v1/notifications/")
        assert response.status_code == 200
        assert response.json()["data"] == []

    def test_notification_detail(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        notification = make_notification(recipient_id=self.fake_user_id)
        DjangoNotificationRepository().save(notification)
        response = api_client.get(f"/api/v1/notifications/{notification.id}")
        assert response.status_code == 200
        assert response.json()["data"]["body"] == notification.body.value

    def test_notification_detail_not_found(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get(f"/api/v1/notifications/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_statistics(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        DjangoNotificationRepository().save(make_notification(recipient_id=self.fake_user_id))
        response = api_client.get("/api/v1/notifications/statistics")
        assert response.status_code == 200
        assert "counts_by_status" in response.json()["data"]

    def test_preferences_missing_creates_the_all_enabled_default(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.get("/api/v1/notifications/preferences")
        assert response.status_code == 200
        assert all(entry["enabled"] for entry in response.json()["data"]["entries"])
        assert DjangoNotificationPreferenceRepository().get_by_user_id(self.fake_user_id) is not None

    def test_preferences_returns_full_matrix(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        preference = make_preference(user_id=self.fake_user_id)
        DjangoNotificationPreferenceRepository().save(preference)
        response = api_client.get("/api/v1/notifications/preferences")
        assert response.status_code == 200
        assert len(response.json()["data"]["entries"]) == 5 * 3  # 5 channels x 3 types

    # --- Honest 501 mutation endpoints, all 6 -----------------------------

    def test_create_notification_returns_honest_501(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/notifications/", {"recipient_id": str(uuid.uuid4()), "notification_type": "transactional", "title": "Shipped", "body": "x"}, format="json")
        assert response.status_code == 501
        assert "Application Service" in response.json()["data"]["detail"]

    def test_create_notification_validates_before_501(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/notifications/", {"recipient_id": str(uuid.uuid4()), "notification_type": "transactional", "title": "", "body": "x"}, format="json")
        assert response.status_code == 422

    def test_mark_seen_returns_honest_501(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        notification = make_notification(recipient_id=self.fake_user_id)
        DjangoNotificationRepository().save(notification)
        response = api_client.post(f"/api/v1/notifications/{notification.id}/seen", {}, format="json")
        assert response.status_code == 501

    def test_mark_read_returns_honest_501(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        notification = make_notification(recipient_id=self.fake_user_id)
        DjangoNotificationRepository().save(notification)
        response = api_client.post(f"/api/v1/notifications/{notification.id}/read", {}, format="json")
        assert response.status_code == 501

    def test_cancel_returns_honest_501(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        notification = make_notification(recipient_id=self.fake_user_id)
        DjangoNotificationRepository().save(notification)
        response = api_client.post(f"/api/v1/notifications/{notification.id}/cancel", {}, format="json")
        assert response.status_code == 501

    @staticmethod
    def _enabled(response, channel, notification_type):
        return next(e["enabled"] for e in response.json()["data"]["entries"] if e["channel"] == channel and e["notification_type"] == notification_type)

    def test_disable_then_enable_preference_round_trips(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        payload = {"channel": "telegram", "notification_type": "promotional"}

        disabled = api_client.post("/api/v1/notifications/preferences/disable", payload, format="json")
        assert disabled.status_code == 200
        assert self._enabled(disabled, "telegram", "promotional") is False
        assert self._enabled(disabled, "telegram", "transactional") is True
        assert self._enabled(api_client.get("/api/v1/notifications/preferences"), "telegram", "promotional") is False

        enabled = api_client.post("/api/v1/notifications/preferences/enable", payload, format="json")
        assert enabled.status_code == 200
        assert self._enabled(enabled, "telegram", "promotional") is True

    def test_preference_toggle_validates_payload(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        response = api_client.post("/api/v1/notifications/preferences/disable", {"channel": "pigeon", "notification_type": "promotional"}, format="json")
        assert response.status_code == 422

    # --- IDOR / cross-user isolation, verified end-to-end -----------------

    def test_user_cannot_access_another_users_notification_detail(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        other_users_notification = make_notification()  # a different recipient_id
        DjangoNotificationRepository().save(other_users_notification)
        response = api_client.get(f"/api/v1/notifications/{other_users_notification.id}")
        assert response.status_code == 403

    def test_user_cannot_mark_another_users_notification_seen(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        other_users_notification = make_notification()
        DjangoNotificationRepository().save(other_users_notification)
        response = api_client.post(f"/api/v1/notifications/{other_users_notification.id}/seen", {}, format="json")
        assert response.status_code == 403

    def test_user_cannot_cancel_another_users_notification(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        other_users_notification = make_notification()
        DjangoNotificationRepository().save(other_users_notification)
        response = api_client.post(f"/api/v1/notifications/{other_users_notification.id}/cancel", {}, format="json")
        assert response.status_code == 403

    def test_all_notification_scoped_mutations_404_when_notification_missing(self, api_client):
        api_client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
        missing_id = uuid.uuid4()
        assert api_client.post(f"/api/v1/notifications/{missing_id}/seen", {}, format="json").status_code == 404
        assert api_client.post(f"/api/v1/notifications/{missing_id}/read", {}, format="json").status_code == 404
        assert api_client.post(f"/api/v1/notifications/{missing_id}/cancel", {}, format="json").status_code == 404
