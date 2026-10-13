"""
In-memory fakes implementing application/ports.py's Protocols, used
across application-layer tests -- per Django Implementation Blueprint
§11's rule that application-layer unit tests fake their repository/
gateway ports rather than hitting a real database.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

from apps.identity.domain.services import OTPChallengeState, TokenPolicy
from apps.identity.domain.value_objects import PhoneNumber
from core.clock import Clock


class FakeUserRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, object] = {}

    def get_by_id(self, user_id):
        return self.by_id.get(user_id)

    def get_by_phone_number(self, phone_number: PhoneNumber):
        for user in self.by_id.values():
            if user.phone_number.value == phone_number.value:
                return user
        return None

    def save(self, user):
        self.by_id[user.id] = user
        return user

    def exists_with_username(self, username: str, exclude_user_id=None) -> bool:
        return any(u.username == username and u.id != exclude_user_id for u in self.by_id.values())

    def list_for_admin(self, status=None, query=None, page=1, page_size=20):
        users = list(self.by_id.values())
        if status:
            users = [u for u in users if u.status.value == status]
        return users[(page - 1) * page_size : page * page_size], len(users)


class FakeOTPChallengeRepository:
    """
    Redesigned as part of a real defect fix: previously mirrored the
    Django repository's own now-fixed bug (every mutation operated on
    "whichever challenge is latest for this phone number right now"
    rather than a specific challenge's identity). Now keyed by
    `id`, matching the corrected `OTPChallengeRepository` Port
    exactly, so tests can genuinely exercise the fix rather than a
    fake that could never reproduce the race it's meant to guard
    against.
    """

    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, OTPChallengeState] = {}
        self._ids_by_phone: dict[str, list[uuid.UUID]] = {}

    def create(self, phone_number: PhoneNumber, code_hash: str, expires_at: datetime) -> OTPChallengeState:
        state = OTPChallengeState(id=uuid.uuid4(), code_hash=code_hash, expires_at=expires_at, attempt_count=0, consumed_at=None, created_at=Clock.now(), phone_number=phone_number.value)
        self._by_id[state.id] = state
        self._ids_by_phone.setdefault(phone_number.value, []).append(state.id)
        return state

    def get_latest(self, phone_number: PhoneNumber):
        ids = self._ids_by_phone.get(phone_number.value, [])
        return self._by_id[ids[-1]] if ids else None

    def find_active_by_code_hash(self, code_hash: str):
        candidates = [s for s in self._by_id.values() if s.code_hash == code_hash and s.consumed_at is None and s.expires_at > Clock.now()]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.created_at)

    def count_requested_since(self, phone_number: PhoneNumber, since: datetime) -> int:
        ids = self._ids_by_phone.get(phone_number.value, [])
        return len([i for i in ids if self._by_id[i].created_at >= since])

    def increment_attempt(self, challenge_id: uuid.UUID) -> None:
        state = self._by_id.get(challenge_id)
        if state is not None:
            self._by_id[challenge_id] = OTPChallengeState(
                id=state.id, code_hash=state.code_hash, expires_at=state.expires_at,
                attempt_count=state.attempt_count + 1, consumed_at=state.consumed_at, created_at=state.created_at,
            )

    def mark_consumed(self, challenge_id: uuid.UUID) -> bool:
        """Mirrors the real repository's now-atomic, idempotency-safe contract: returns False (and makes no change) if already consumed."""
        state = self._by_id.get(challenge_id)
        if state is None or state.consumed_at is not None:
            return False
        self._by_id[challenge_id] = OTPChallengeState(
            id=state.id, code_hash=state.code_hash, expires_at=state.expires_at,
            attempt_count=state.attempt_count, consumed_at=Clock.now(), created_at=state.created_at,
        )
        return True


class FakeUserSessionRepository:
    def __init__(self) -> None:
        self.by_id: dict[uuid.UUID, object] = {}
        self.revoked_token_records: dict[str, tuple[uuid.UUID, uuid.UUID]] = {}
        """token_hash -> (user_id, session_id) -- mirrors RevokedTokenRecord's real, minimal shape, so is_token_reuse() below can be tested without a real database."""

    def create(self, session):
        self.by_id[session.id] = session
        return session

    def get_by_id(self, session_id):
        return self.by_id.get(session_id)

    def get_by_refresh_token_hash(self, token_hash: str):
        for s in self.by_id.values():
            if s.refresh_token_hash == token_hash and s.revoked_at is None:
                return s
        return None

    def list_active_for_user(self, user_id):
        return [s for s in self.by_id.values() if s.user_id == user_id and s.revoked_at is None]

    def revoke(self, session_id) -> None:
        session = self.by_id.get(session_id)
        if session is not None and session.revoked_at is None:
            self.revoked_token_records[session.refresh_token_hash] = (session.user_id, session.id)
            session.revoked_at = Clock.now()

    def revoke_all_for_user(self, user_id) -> None:
        for s in self.by_id.values():
            if s.user_id == user_id and s.revoked_at is None:
                self.revoked_token_records[s.refresh_token_hash] = (s.user_id, s.id)
                s.revoked_at = Clock.now()

    def touch_last_activity(self, session_id) -> None:
        pass

    def is_token_reuse(self, token_hash: str) -> tuple[uuid.UUID, uuid.UUID] | None:
        """Mirrors DjangoUserSessionRepository's own (user_id, session_id) return shape exactly, so Application-layer tests exercise the real Port contract, not an ad-hoc fake shape."""
        return self.revoked_token_records.get(token_hash)


class FakeRoleRepository:
    def __init__(self) -> None:
        self.by_code: dict[str, object] = {}

    def get_by_code(self, code: str):
        return self.by_code.get(code)

    def get_by_id(self, role_id):
        return next((r for r in self.by_code.values() if r.id == role_id), None)

    def list_all(self):
        return list(self.by_code.values())


class FakeRoleAssignmentRepository:
    def __init__(self) -> None:
        self.assignments: list = []
        self.permission_codes_by_role: dict[uuid.UUID, set[str]] = {}

    def assign(self, assignment):
        self.assignments.append(assignment)
        return assignment

    def exists(self, user_id, role_id, store_id) -> bool:
        return any(a.user_id == user_id and a.role_id == role_id and a.store_id == store_id for a in self.assignments)

    def list_effective_permission_codes(self, user_id, store_id=None) -> set[str]:
        codes: set[str] = set()
        for a in self.assignments:
            if a.user_id == user_id and (a.store_id == store_id or a.store_id is None):
                codes |= self.permission_codes_by_role.get(a.role_id, set())
        return codes

    def list_role_codes_for_user(self, user_id) -> list[str]:
        return [a.role_id for a in self.assignments if a.user_id == user_id]

    def list_store_ids_for_user(self, user_id) -> set[uuid.UUID]:
        return {a.store_id for a in self.assignments if a.user_id == user_id and a.store_id is not None}

    def remove(self, assignment_id):
        hit = next((a for a in self.assignments if a.id == assignment_id), None)
        if hit is None:
            return None
        self.assignments.remove(hit)
        return {"user_id": hit.user_id, "role_id": hit.role_id, "store_id": hit.store_id}


@dataclass(frozen=True, slots=True)
class _FakeTokenPair:
    access_token: str
    refresh_token: str
    refresh_token_hash: str
    refresh_expires_at: datetime


class FakeTokenIssuer:
    """Deterministic fake -- no real JWT signing, just distinguishable tokens per call for test assertions."""

    def __init__(self) -> None:
        self.issued: list[uuid.UUID] = []
        self.blacklisted: list[str] = []
        self._counter = 0

    def issue(self, user_id: uuid.UUID):
        self._counter += 1
        raw_refresh = f"refresh-token-{self._counter}"
        self.issued.append(user_id)
        return _FakeTokenPair(
            access_token=f"access-token-{self._counter}",
            refresh_token=raw_refresh,
            refresh_token_hash=self.hash_refresh_token(raw_refresh),
            refresh_expires_at=TokenPolicy.refresh_token_expiry(),
        )

    def blacklist_refresh_token(self, raw_refresh_token: str) -> None:
        self.blacklisted.append(raw_refresh_token)

    def hash_refresh_token(self, raw_refresh_token: str) -> str:
        return hashlib.sha256(raw_refresh_token.encode()).hexdigest()


class FakeOTPProvider:
    def __init__(self, always_fails: bool = False, raises: Exception | None = None) -> None:
        self.sent: list[tuple[str, str]] = []
        self._always_fails = always_fails
        self._raises = raises

    def send_otp(self, phone_number: PhoneNumber, code: str) -> bool:
        if self._raises is not None:
            raise self._raises
        self.sent.append((phone_number.value, code))
        return not self._always_fails


def fake_hash_otp_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def collect_events(sink: list[tuple[str, dict]]):
    def _stage(events: list[tuple[str, dict]]) -> None:
        sink.extend(events)

    return _stage
