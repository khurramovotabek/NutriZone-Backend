"""
Repository integration tests -- require a real PostgreSQL database
(Django Implementation Blueprint §11: no SQLite, ever), hence every
test here is `@pytest.mark.django_db` and `@pytest.mark.integration`,
never `unit`. These verify the ORM <-> domain-object mapping
repositories.py is responsible for (Django Implementation Blueprint
§6), which cannot be meaningfully exercised against fakes.
"""
from __future__ import annotations

import uuid

import pytest

from apps.identity.domain.value_objects import PhoneNumber
from apps.identity.infrastructure.repositories import DjangoRoleAssignmentRepository, DjangoRoleRepository, DjangoUserRepository
from apps.identity.infrastructure import models as orm

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


class TestDjangoUserRepository:
    def test_save_then_get_by_id_round_trips(self):
        from apps.identity.domain.aggregates import User

        repo = DjangoUserRepository()
        user = User(id=uuid.uuid4(), phone_number=PhoneNumber("+998901234567"), full_name="Repo Test")
        repo.save(user)

        fetched = repo.get_by_id(user.id)
        assert fetched is not None
        assert fetched.phone_number.value == "+998901234567"
        assert fetched.full_name == "Repo Test"

    def test_get_by_phone_number_finds_saved_user(self):
        from apps.identity.domain.aggregates import User

        repo = DjangoUserRepository()
        user = User(id=uuid.uuid4(), phone_number=PhoneNumber("+998907654321"), full_name="Phone Lookup")
        repo.save(user)

        fetched = repo.get_by_phone_number(PhoneNumber("+998907654321"))
        assert fetched is not None
        assert fetched.id == user.id

    def test_get_by_id_returns_none_when_missing(self):
        repo = DjangoUserRepository()
        assert repo.get_by_id(uuid.uuid4()) is None

    def test_exists_with_username_respects_exclusion(self):
        from apps.identity.domain.aggregates import User

        repo = DjangoUserRepository()
        user = User(id=uuid.uuid4(), phone_number=PhoneNumber("+998901112233"), full_name="Username Test", username="uniquename")
        repo.save(user)

        assert repo.exists_with_username("uniquename") is True
        assert repo.exists_with_username("uniquename", exclude_user_id=user.id) is False

    def test_list_for_admin_filters_by_status(self):
        from apps.identity.domain.aggregates import User
        from apps.identity.domain.enums import UserStatus

        repo = DjangoUserRepository()
        active = User(id=uuid.uuid4(), phone_number=PhoneNumber("+998900000001"), full_name="Active", status=UserStatus.ACTIVE)
        blocked = User(id=uuid.uuid4(), phone_number=PhoneNumber("+998900000002"), full_name="Blocked", status=UserStatus.BLOCKED)
        repo.save(active)
        repo.save(blocked)

        results, total = repo.list_for_admin(status="blocked")
        assert total == 1
        assert results[0].id == blocked.id

    def test_soft_deleted_user_is_excluded_by_default_manager(self):
        from apps.identity.domain.aggregates import User

        repo = DjangoUserRepository()
        user = User(id=uuid.uuid4(), phone_number=PhoneNumber("+998900000099"), full_name="To Delete")
        repo.save(user)

        row = orm.User.objects.get(id=user.id)
        row.delete()  # soft delete, per common/models/base.py

        assert orm.User.objects.filter(id=user.id).first() is None  # default manager excludes it
        assert orm.User.all_objects.filter(id=user.id).first() is not None  # still present in all_objects


class TestDjangoRoleAssignmentRepository:
    def test_list_effective_permission_codes_aggregates_across_roles(self):
        role_a = orm.Role.objects.create(code="role_a", name="Role A")
        role_b = orm.Role.objects.create(code="role_b", name="Role B")
        perm_view = orm.Permission.objects.create(code="identity.user.view")
        perm_suspend = orm.Permission.objects.create(code="identity.user.suspend")
        orm.RolePermission.objects.create(role=role_a, permission=perm_view)
        orm.RolePermission.objects.create(role=role_b, permission=perm_suspend)

        user = orm.User.objects.create(phone_number="+998900000077", full_name="RBAC Test")
        orm.UserRole.objects.create(user=user, role=role_a)
        orm.UserRole.objects.create(user=user, role=role_b)

        repo = DjangoRoleAssignmentRepository()
        codes = repo.list_effective_permission_codes(user.id)
        assert codes == {"identity.user.view", "identity.user.suspend"}

    def test_exists_detects_duplicate_assignment(self):
        role = orm.Role.objects.create(code="dup_role", name="Dup Role")
        user = orm.User.objects.create(phone_number="+998900000088", full_name="Dup Test")
        orm.UserRole.objects.create(user=user, role=role)

        repo = DjangoRoleAssignmentRepository()
        assert repo.exists(user.id, role.id, None) is True
        assert repo.exists(user.id, role.id, uuid.uuid4()) is False


class TestDjangoRoleRepository:
    def test_get_by_code_returns_role(self):
        orm.Role.objects.create(code="test_role_lookup", name="Test Role Lookup")
        role = DjangoRoleRepository().get_by_code("test_role_lookup")
        assert role is not None
        assert role.name == "Test Role Lookup"

    def test_get_by_code_returns_none_when_missing(self):
        assert DjangoRoleRepository().get_by_code("does_not_exist") is None
