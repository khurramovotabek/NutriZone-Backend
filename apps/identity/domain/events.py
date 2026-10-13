"""
Identity domain events.

These are the payload contracts for the five events the mission names:
UserRegistered, UserAuthenticated, UserBlocked, UserProfileUpdated,
UserRoleAssigned. Every one is registered against
`core.events.registry.registry` (see apps/identity/apps.py's
`ready()` hook) and against `shared/event_contracts/identity.py`
before any Application Service emits it, per MIC §7's "a module may
not invent a new event type during implementation without first
amending the catalogue" rule -- registration IS that amendment,
recorded in code.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class UserRegistered:
    user_id: uuid.UUID
    phone_number: str
    registered_via: str  # AuthProviderType value

    def to_payload(self) -> dict:
        return {**asdict(self), "user_id": str(self.user_id)}


@dataclass(frozen=True, slots=True)
class UserAuthenticated:
    user_id: uuid.UUID
    session_id: uuid.UUID
    provider_type: str
    ip_address: str | None

    def to_payload(self) -> dict:
        return {**asdict(self), "user_id": str(self.user_id), "session_id": str(self.session_id)}


@dataclass(frozen=True, slots=True)
class UserBlocked:
    user_id: uuid.UUID
    reason: str | None

    def to_payload(self) -> dict:
        return {**asdict(self), "user_id": str(self.user_id)}


@dataclass(frozen=True, slots=True)
class UserProfileUpdated:
    user_id: uuid.UUID
    before: dict
    after: dict

    def to_payload(self) -> dict:
        return {**asdict(self), "user_id": str(self.user_id)}


@dataclass(frozen=True, slots=True)
class UserRoleAssigned:
    user_id: uuid.UUID
    role_id: uuid.UUID
    role_code: str
    store_id: uuid.UUID | None

    def to_payload(self) -> dict:
        return {
            **asdict(self),
            "user_id": str(self.user_id),
            "role_id": str(self.role_id),
            "store_id": str(self.store_id) if self.store_id else None,
        }


@dataclass(frozen=True, slots=True)
class SuspiciousLoginDetected:
    """Raised by RefreshToken when a rotated-out token is reused (Architecture Review §14)."""

    user_id: uuid.UUID
    session_id: uuid.UUID
    ip_address: str | None

    def to_payload(self) -> dict:
        return {**asdict(self), "user_id": str(self.user_id), "session_id": str(self.session_id)}


@dataclass(frozen=True, slots=True)
class SessionRevoked:
    user_id: uuid.UUID
    session_id: uuid.UUID
    revoked_by: uuid.UUID | None  # None when self-revoked

    def to_payload(self) -> dict:
        return {
            **asdict(self),
            "user_id": str(self.user_id),
            "session_id": str(self.session_id),
            "revoked_by": str(self.revoked_by) if self.revoked_by else None,
        }
