"""
NutriZone Admin "Roles & Permissions Overview" tests -- closes a real,
confirmed gap: Role/Permission/RolePermission/UserRole had real
relational data but zero visual overview, only the bare, standard
Django admin grids. Real database fixtures throughout, matching this
project's own established "Real Data Verification" discipline.
"""
from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from apps.identity.infrastructure.models import Permission, Role, RolePermission, User, UserRole
from apps.identity.infrastructure.roles_overview import RolePermissionOverviewAggregator

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


@pytest.fixture
def staff_client():
    AuthUser = get_user_model()
    user = AuthUser.objects.create(username=f"nz_staff_{uuid.uuid4().hex[:8]}", is_staff=True, is_superuser=True)
    user.set_password("pw")
    user.save()
    client = Client()
    client.force_login(user)
    return client


class TestRolePermissionOverviewAggregator:
    def test_role_lists_its_real_assigned_permissions_and_user_count(self):
        role = Role.objects.create(id=uuid.uuid4(), code="test_manager", name="Test Manager", is_system_role=False)
        perm1 = Permission.objects.create(id=uuid.uuid4(), code="orders.view", description="View orders")
        perm2 = Permission.objects.create(id=uuid.uuid4(), code="orders.edit", description="Edit orders")
        RolePermission.objects.create(id=uuid.uuid4(), role=role, permission=perm1)
        RolePermission.objects.create(id=uuid.uuid4(), role=role, permission=perm2)
        user = User.objects.create(id=uuid.uuid4(), phone_number=f"+99890{uuid.uuid4().int % 10000000:07d}", status="active", full_name="Test User")
        UserRole.objects.create(id=uuid.uuid4(), user=user, role=role)

        roles = RolePermissionOverviewAggregator().roles_with_permissions()
        matching = next(r for r in roles if r["code"] == "test_manager")
        assert matching["permission_count"] == 2
        assert {p["code"] for p in matching["permissions"]} == {"orders.view", "orders.edit"}
        assert matching["user_count"] == 1

    def test_unassigned_permission_is_flagged_and_assigned_ones_are_not(self):
        role = Role.objects.create(id=uuid.uuid4(), code="test_role_2", name="Test Role 2")
        assigned = Permission.objects.create(id=uuid.uuid4(), code="assigned.permission", description="Assigned")
        RolePermission.objects.create(id=uuid.uuid4(), role=role, permission=assigned)
        orphan = Permission.objects.create(id=uuid.uuid4(), code="orphan.permission", description="Never assigned")

        unassigned = RolePermissionOverviewAggregator().unassigned_permissions()
        codes = {p["code"] for p in unassigned}
        assert "orphan.permission" in codes
        assert "assigned.permission" not in codes

    def test_role_with_no_permissions_reports_zero_not_an_error(self):
        Role.objects.create(id=uuid.uuid4(), code="empty_role", name="Empty Role")
        roles = RolePermissionOverviewAggregator().roles_with_permissions()
        matching = next(r for r in roles if r["code"] == "empty_role")
        assert matching["permission_count"] == 0
        assert matching["permissions"] == []
        assert matching["user_count"] == 0


class TestRolesOverviewPage:
    def test_page_renders_real_role_and_permission_data(self, staff_client):
        role = Role.objects.create(id=uuid.uuid4(), code="warehouse_staff", name="Warehouse Staff", is_system_role=True)
        perm = Permission.objects.create(id=uuid.uuid4(), code="inventory.manage", description="Manage inventory")
        RolePermission.objects.create(id=uuid.uuid4(), role=role, permission=perm)

        response = staff_client.get("/django-admin/roles-overview/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Warehouse Staff" in content
        assert "inventory.manage" in content
        assert "Tizim" in content

    def test_page_requires_staff_authentication(self):
        response = Client().get("/django-admin/roles-overview/")
        assert response.status_code in (302, 403)

    def test_page_is_linked_from_the_dashboard_home(self, staff_client):
        response = staff_client.get("/django-admin/")
        assert response.status_code == 200
        assert "roles-overview" in response.content.decode()
