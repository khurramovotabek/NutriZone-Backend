"""
Phase 03B Dashboard completion: Customer Statistics. Identity had no
statistics selector or endpoint at all.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.identity.infrastructure import models as orm
from common.permissions import HasPermissionCode

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class _AllowAllResolver:
    def user_has_permission(self, user_id, permission_code, store_id=None) -> bool:
        return True


@pytest.fixture
def staff_client(monkeypatch):
    original = HasPermissionCode.resolver
    HasPermissionCode.resolver = _AllowAllResolver()
    fake_user = SimpleNamespace(id=uuid.uuid4(), is_authenticated=True, store_ids=set())
    monkeypatch.setattr(
        "apps.identity.infrastructure.authentication.JWTIdentityAuthentication.authenticate",
        lambda self, request: (fake_user, None),
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer fake-token")
    yield client
    HasPermissionCode.resolver = original


class TestUserStatistics:
    def test_returns_counts_by_status_and_totals(self, staff_client):
        orm.User.objects.create(phone_number="+998900001001", status="active")
        orm.User.objects.create(phone_number="+998900001002", status="active")
        orm.User.objects.create(phone_number="+998900001003", status="blocked")

        response = staff_client.get("/api/v1/identity/admin/users/statistics")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["active_customers"] == 2
        assert data["counts_by_status"]["active"] == 2
        assert data["counts_by_status"]["blocked"] == 1
        assert data["total_customers"] == 3

    def test_soft_deleted_users_excluded(self, staff_client):
        user = orm.User.objects.create(phone_number="+998900001004", status="active")
        user.is_deleted = True
        user.save()

        response = staff_client.get("/api/v1/identity/admin/users/statistics")
        assert response.status_code == 200
        assert response.json()["data"]["total_customers"] == 0

    def test_unauthenticated_rejected(self):
        response = APIClient().get("/api/v1/identity/admin/users/statistics")
        assert response.status_code == 401
