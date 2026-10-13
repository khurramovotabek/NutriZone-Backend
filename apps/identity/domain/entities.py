"""
Identity domain entities (non-root members of the User/Role aggregates).

Plain, framework-free dataclasses -- these are in-memory representations
the domain/application layers reason about; `infrastructure/models.py`
maps them to/from Django ORM rows via the repository layer, which is
the only place these two representations meet.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from apps.identity.domain.enums import AuthProviderType, DeviceType


@dataclass(slots=True)
class AuthMethod:
    """One (user, provider) authentication binding -- Database Blueprint §4.1 `identity.auth_methods`."""

    id: uuid.UUID
    user_id: uuid.UUID
    provider_type: AuthProviderType
    external_id: str | None = None
    credential_hash: str | None = None
    last_used_at: datetime | None = None


@dataclass(slots=True)
class Device:
    """Registered device -- Database Blueprint §4.1 `identity.devices`."""

    id: uuid.UUID
    user_id: uuid.UUID | None
    device_type: DeviceType
    device_name: str | None = None
    push_token: str | None = None
    is_trusted: bool = False


@dataclass(slots=True)
class UserSession:
    """
    An active refresh-token session for one device -- Database
    Blueprint §4.1 `identity.user_sessions`. Mission-required fields:
    device_name, device_type, ip_address, last_activity,
    refresh_token_hash, expired_at.
    """

    id: uuid.UUID
    user_id: uuid.UUID
    device_id: uuid.UUID | None
    device_name: str | None
    device_type: DeviceType
    refresh_token_hash: str
    ip_address: str | None
    user_agent: str | None
    last_activity: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


@dataclass(slots=True)
class Permission:
    """A single fine-grained permission -- e.g. 'orders.view'."""

    id: uuid.UUID
    code: str
    description: str = ""


@dataclass(slots=True)
class RoleAssignment:
    """One (user, role, optional store scope) grant -- Database Blueprint §4.1 `identity.user_roles`."""

    id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    store_id: uuid.UUID | None = None
