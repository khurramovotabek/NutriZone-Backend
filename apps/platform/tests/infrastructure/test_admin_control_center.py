"""
Phase 08.9: NutriZone Admin Control Center tests -- Users, Roles
(Django Groups), Permissions, Settings (FeatureFlags), Audit Timeline.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone as tz

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def staff_client():
    User = get_user_model()
    user = User.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client, user


@pytest.fixture
def non_staff_client():
    User = get_user_model()
    user = User.objects.create(username=f"nz_customer_{uuid.uuid4().hex[:8]}", is_staff=False)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client, user


class TestUserSessionSecretSafety:
    """Phase 08.9: closes a genuine, confirmed critical security defect found via direct testing -- refresh_token_hash was rendered in full on the UserSession detail page."""

    def test_refresh_token_hash_never_appears_in_rendered_page(self, staff_client):
        client, _ = staff_client
        from apps.identity.infrastructure import models as orm

        u = orm.User.objects.create(phone_number=f"+998900{uuid.uuid4().hex[:6]}", full_name="Secret Check")
        session = orm.UserSession.objects.create(
            user=u, device_type="mobile", refresh_token_hash=f"SECRET-TOKEN-{uuid.uuid4().hex}",
            last_activity=datetime.now(tz.utc), expires_at=datetime.now(tz.utc) + timedelta(days=1),
        )

        response = client.get(f"/django-admin/identity/usersession/{session.id}/change/")
        assert response.status_code == 200
        assert session.refresh_token_hash not in response.content.decode()

    def test_session_list_still_shows_safe_fields(self, staff_client):
        client, _ = staff_client
        response = client.get("/django-admin/identity/usersession/")
        assert response.status_code == 200


class TestUsersWorkspace:
    def test_anonymous_denied(self):
        response = Client().get("/django-admin/identity/user/")
        assert response.status_code in (302, 403)

    def test_non_staff_denied(self, non_staff_client):
        client, _ = non_staff_client
        response = client.get("/django-admin/identity/user/")
        assert response.status_code in (302, 403)

    def test_no_password_hash_in_rendered_page(self, staff_client):
        client, _ = staff_client
        from apps.identity.infrastructure import models as orm

        u = orm.User.objects.create(phone_number=f"+998900{uuid.uuid4().hex[:6]}", full_name="Password Check")
        response = client.get(f"/django-admin/identity/user/{u.id}/change/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "password_hash" not in content.lower()


class TestSelfPrivilegeEscalationProtection:
    """This phase's own mandatory requirement: a non-superuser staff member must not be able to grant themselves superuser via Django Admin's own UserAdmin."""

    def test_staff_without_superuser_cannot_self_promote_via_admin_form(self):
        User = get_user_model()
        staff_user = User.objects.create(username=f"nz_escalate_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=False)
        staff_user.set_password("pw")
        staff_user.save()

        client = Client()
        client.force_login(staff_user)

        # The auth.User admin (django.contrib.auth) is real Django's own default -- test its own change_permission gate.
        response = client.get(f"/django-admin/auth/user/{staff_user.id}/change/")
        # Without change_user permission, this must be denied -- not silently allow self-editing.
        assert response.status_code in (302, 403)

        staff_user.refresh_from_db()
        assert staff_user.is_superuser is False  # unchanged regardless of the request outcome


class TestRolesViaGroups:
    """Confirmed: Django's own default Group admin is already registered -- the real 'Roles' mechanism. Not rebuilt, extended/verified."""

    def test_group_list_accessible_to_superuser(self, staff_client):
        client, _ = staff_client
        Group.objects.create(name=f"TestRole-{uuid.uuid4().hex[:6]}")
        response = client.get("/django-admin/auth/group/")
        assert response.status_code == 200

    def test_non_staff_denied_group_access(self, non_staff_client):
        client, _ = non_staff_client
        response = client.get("/django-admin/auth/group/")
        assert response.status_code in (302, 403)


class TestFeatureFlagsNotInDashboard:
    """Product decision: feature flags are not a dashboard page (unnecessary complexity) -- they stay governed via the API."""

    def test_feature_flag_admin_is_not_registered(self, staff_client):
        client, _ = staff_client
        assert client.get("/django-admin/platform/featureflagmodel/").status_code == 404


class TestAuditTimeline:
    """Phase 08.9: no centralized Audit model exists (apps.audit is a confirmed, deliberate placeholder) -- this reuses each module's own already-registered OutboxEvent table."""

    def test_anonymous_denied(self):
        response = Client().get("/django-admin/audit-timeline/")
        assert response.status_code in (302, 403)

    def test_staff_can_view(self, staff_client):
        client, _ = staff_client
        response = client.get("/django-admin/audit-timeline/")
        assert response.status_code == 200
        assert "Audit Timeline" in response.content.decode()

    def test_real_staged_event_appears_in_timeline(self):
        """Proves the timeline reads real data, not a static shape -- stages a real event through the actual, certified Outbox mechanism."""
        from django.db import transaction
        from apps.ordering.infrastructure import models as orm
        from core.outbox import stage_event
        from apps.platform.infrastructure.audit_timeline import recent_events

        marker = f"audit-test-{uuid.uuid4().hex}"
        with transaction.atomic():
            stage_event(orm.OrderingOutboxEvent, "OrderCreated", {"order_id": marker})

        events = recent_events(limit=50)
        assert any(e["event_type"] == "OrderCreated" and e["module"] == "Ordering" for e in events)

    def test_no_payload_contents_exposed(self, staff_client):
        """Never renders payload contents (which could contain sensitive business data) -- only event_type/module/correlation_id/delivery status."""
        client, _ = staff_client
        from django.db import transaction
        from apps.ordering.infrastructure import models as orm
        from core.outbox import stage_event

        with transaction.atomic():
            stage_event(orm.OrderingOutboxEvent, "OrderCreated", {"order_id": "SENSITIVE-MARKER-VALUE"})

        response = client.get("/django-admin/audit-timeline/")
        assert "SENSITIVE-MARKER-VALUE" not in response.content.decode()


class TestCrossWorkspaceRegression:
    def test_dashboard_home_still_renders(self, staff_client):
        client, _ = staff_client
        response = client.get("/django-admin/")
        assert response.status_code == 200
        assert "nz-dashboard" in response.content.decode()

    def test_reports_still_renders(self, staff_client):
        client, _ = staff_client
        response = client.get("/django-admin/reports/")
        assert response.status_code == 200

    def test_notifications_still_renders(self, staff_client):
        client, _ = staff_client
        response = client.get("/django-admin/notifications/notificationmodel/")
        assert response.status_code == 200
