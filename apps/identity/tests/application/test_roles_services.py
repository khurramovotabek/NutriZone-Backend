from __future__ import annotations

import uuid

import pytest

from apps.identity.application.services.roles import AssignRole, CheckPermission
from apps.identity.domain.aggregates import Role
from apps.identity.domain.exceptions import RoleAlreadyAssignedError
from apps.identity.tests.application.fakes import FakeRoleAssignmentRepository, FakeRoleRepository, collect_events
from common.exceptions import ResourceNotFound


@pytest.mark.django_db
class TestAssignRole:
    """Marked django_db: AssignRole.execute uses @transaction.atomic."""

    def test_assigns_role_and_stages_event(self):
        role_repo = FakeRoleRepository()
        role_repo.by_code["store_manager"] = Role(id=uuid.uuid4(), code="store_manager", name="Store Manager")
        assignment_repo = FakeRoleAssignmentRepository()
        events: list = []
        service = AssignRole(role_repo=role_repo, assignment_repo=assignment_repo, stage_events=collect_events(events))

        user_id = uuid.uuid4()
        service.execute(user_id=user_id, role_code="store_manager")

        assert len(assignment_repo.assignments) == 1
        assert any(e[0] == "UserRoleAssigned" for e in events)

    def test_unknown_role_code_raises_not_found(self):
        role_repo = FakeRoleRepository()
        service = AssignRole(role_repo=role_repo, assignment_repo=FakeRoleAssignmentRepository(), stage_events=collect_events([]))
        with pytest.raises(ResourceNotFound):
            service.execute(user_id=uuid.uuid4(), role_code="does_not_exist")

    def test_duplicate_assignment_raises(self):
        role_repo = FakeRoleRepository()
        role = Role(id=uuid.uuid4(), code="customer", name="Customer")
        role_repo.by_code["customer"] = role
        assignment_repo = FakeRoleAssignmentRepository()
        service = AssignRole(role_repo=role_repo, assignment_repo=assignment_repo, stage_events=collect_events([]))

        user_id = uuid.uuid4()
        service.execute(user_id=user_id, role_code="customer")
        with pytest.raises(RoleAlreadyAssignedError):
            service.execute(user_id=user_id, role_code="customer")

    def test_store_scoped_assignment_is_independent_of_global(self):
        role_repo = FakeRoleRepository()
        role = Role(id=uuid.uuid4(), code="store_manager", name="Store Manager")
        role_repo.by_code["store_manager"] = role
        assignment_repo = FakeRoleAssignmentRepository()
        service = AssignRole(role_repo=role_repo, assignment_repo=assignment_repo, stage_events=collect_events([]))

        user_id = uuid.uuid4()
        store_id = uuid.uuid4()
        service.execute(user_id=user_id, role_code="store_manager", store_id=store_id)
        # A different store scope is a distinct assignment, not a duplicate.
        service.execute(user_id=user_id, role_code="store_manager", store_id=uuid.uuid4())
        assert len(assignment_repo.assignments) == 2


@pytest.mark.unit
class TestCheckPermission:
    def test_returns_true_when_permission_is_effective(self):
        assignment_repo = FakeRoleAssignmentRepository()
        role_id = uuid.uuid4()
        assignment_repo.permission_codes_by_role[role_id] = {"identity.user.view"}
        user_id = uuid.uuid4()
        from apps.identity.domain.entities import RoleAssignment

        assignment_repo.assignments.append(RoleAssignment(id=uuid.uuid4(), user_id=user_id, role_id=role_id))

        checker = CheckPermission(assignment_repo=assignment_repo)
        assert checker.user_has_permission(user_id, "identity.user.view") is True

    def test_returns_false_when_permission_not_granted(self):
        assignment_repo = FakeRoleAssignmentRepository()
        checker = CheckPermission(assignment_repo=assignment_repo)
        assert checker.user_has_permission(uuid.uuid4(), "identity.user.suspend") is False

    def test_result_is_cached_on_second_call(self):
        assignment_repo = FakeRoleAssignmentRepository()
        role_id = uuid.uuid4()
        assignment_repo.permission_codes_by_role[role_id] = {"identity.user.view"}
        user_id = uuid.uuid4()
        from apps.identity.domain.entities import RoleAssignment

        assignment_repo.assignments.append(RoleAssignment(id=uuid.uuid4(), user_id=user_id, role_id=role_id))

        checker = CheckPermission(assignment_repo=assignment_repo)
        first = checker.user_has_permission(user_id, "identity.user.view")

        # Remove the assignment entirely -- if the second call still
        # returns True, it proves the cached value was served rather
        # than a fresh (now-false) computation.
        assignment_repo.assignments.clear()
        second = checker.user_has_permission(user_id, "identity.user.view")

        assert first is True
        assert second is True
