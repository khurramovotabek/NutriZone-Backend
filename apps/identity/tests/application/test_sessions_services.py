from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from apps.identity.application.services.sessions import ListOwnSessions, RevokeSession
from apps.identity.domain.entities import UserSession as UserSessionEntity
from apps.identity.domain.enums import DeviceType
from apps.identity.tests.application.fakes import FakeUserSessionRepository, collect_events
from common.exceptions import PermissionDenied, ResourceNotFound
from core.clock import Clock

pytestmark = pytest.mark.unit


def _seed_session(repo: FakeUserSessionRepository, user_id: uuid.UUID) -> UserSessionEntity:
    session = UserSessionEntity(
        id=uuid.uuid4(), user_id=user_id, device_id=None, device_name="Phone", device_type=DeviceType.MOBILE,
        refresh_token_hash="hash", ip_address="1.1.1.1", user_agent="pytest",
        last_activity=Clock.now(), expires_at=Clock.now() + timedelta(days=1),
    )
    repo.create(session)
    return session


class TestListOwnSessions:
    def test_lists_only_active_sessions_for_user(self):
        repo = FakeUserSessionRepository()
        user_id = uuid.uuid4()
        active = _seed_session(repo, user_id)
        revoked = _seed_session(repo, user_id)
        repo.revoke(revoked.id)
        other_user_session = _seed_session(repo, uuid.uuid4())

        results = ListOwnSessions(session_repo=repo).execute(user_id)

        assert {s.id for s in results} == {active.id}


class TestRevokeSession:
    def test_owner_can_revoke_own_session(self):
        repo = FakeUserSessionRepository()
        user_id = uuid.uuid4()
        session = _seed_session(repo, user_id)
        events: list = []

        RevokeSession(session_repo=repo, stage_events=collect_events(events)).execute(
            requesting_user_id=user_id, target_session_id=session.id
        )

        assert repo.by_id[session.id].revoked_at is not None
        assert any(e[0] == "SessionRevoked" for e in events)

    def test_non_owner_cannot_revoke_without_staff_override(self):
        repo = FakeUserSessionRepository()
        owner_id = uuid.uuid4()
        session = _seed_session(repo, owner_id)

        with pytest.raises(PermissionDenied):
            RevokeSession(session_repo=repo, stage_events=collect_events([])).execute(
                requesting_user_id=uuid.uuid4(), target_session_id=session.id
            )

    def test_staff_override_allows_revoking_others_session(self):
        repo = FakeUserSessionRepository()
        owner_id = uuid.uuid4()
        staff_id = uuid.uuid4()
        session = _seed_session(repo, owner_id)
        events: list = []

        RevokeSession(session_repo=repo, stage_events=collect_events(events)).execute(
            requesting_user_id=staff_id, target_session_id=session.id, is_staff_override=True
        )

        assert repo.by_id[session.id].revoked_at is not None
        revoked_event = next(e for e in events if e[0] == "SessionRevoked")
        assert revoked_event[1]["revoked_by"] == str(staff_id)

    def test_revoking_missing_session_raises_not_found(self):
        repo = FakeUserSessionRepository()
        with pytest.raises(ResourceNotFound):
            RevokeSession(session_repo=repo, stage_events=collect_events([])).execute(
                requesting_user_id=uuid.uuid4(), target_session_id=uuid.uuid4()
            )
