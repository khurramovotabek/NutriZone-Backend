"""
Application-layer ports (abstract interfaces).

`application/services/` depends only on these Protocols, never on
`infrastructure/repositories.py` concrete classes directly (Django
Implementation Blueprint §4) -- concrete implementations are wired in
at the `interfaces/api/` or `infrastructure/tasks.py` entrypoint via
constructor injection.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol

from apps.identity.domain.aggregates import Role, User
from apps.identity.domain.entities import AuthMethod, Permission, RoleAssignment, UserSession
from apps.identity.domain.services import OTPChallengeState
from apps.identity.domain.value_objects import PhoneNumber


class UserRepository(Protocol):
    def get_by_id(self, user_id: uuid.UUID) -> User | None: ...

    def get_by_phone_number(self, phone_number: PhoneNumber) -> User | None: ...

    def save(self, user: User) -> User: ...

    def exists_with_username(self, username: str, exclude_user_id: uuid.UUID | None = None) -> bool: ...

    def list_for_admin(
        self,
        status: str | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[User], int]:
        """Returns (page of users, total_count)."""
        ...


class AuthMethodRepository(Protocol):
    def get_by_provider(self, user_id: uuid.UUID, provider_type: str) -> AuthMethod | None: ...

    def save(self, auth_method: AuthMethod) -> AuthMethod: ...


class OTPChallengeRepository(Protocol):
    """Backs the ephemeral `identity.otp_codes` table (Database Blueprint §4.1) -- hard-deleted by a scheduled purge, never soft-deleted."""

    def create(self, phone_number: PhoneNumber, code_hash: str, expires_at: datetime) -> OTPChallengeState: ...

    def get_latest(self, phone_number: PhoneNumber) -> OTPChallengeState | None: ...

    def find_active_by_code_hash(self, code_hash: str) -> OTPChallengeState | None:
        """
        Real, product-required capability: looks up an active
        (unconsumed, unexpired) challenge by its code_hash alone, with
        no phone_number filter. hash_otp_code() is deterministic
        (SHA-256 + a server-side pepper, no per-row salt), so this is
        a real, indexed database lookup -- not a linear scan comparing
        every active challenge in application code. Backs the
        phone-number-free "enter the 6-digit code the bot gave you"
        login flow: the user never types a phone number on the
        website at all.
        """
        ...

    def count_requested_since(self, phone_number: PhoneNumber, since: datetime) -> int: ...

    def increment_attempt(self, challenge_id: uuid.UUID) -> None:
        """A real defect fix: previously keyed by `phone_number`, re-deriving "the latest challenge" independently of whatever challenge was actually read and checked -- a genuine race if a second OTP was requested for the same number between the read and this call. Now targets the exact challenge by id."""
        ...

    def mark_consumed(self, challenge_id: uuid.UUID) -> bool:
        """Same fix as `increment_attempt`, plus a second real defect closed: previously allowed marking an already-consumed challenge consumed again with no signal. Now atomic and idempotency-safe -- returns `True` only if this call was the one that actually transitioned the challenge from unconsumed to consumed, `False` if it was already consumed (by a concurrent request or otherwise)."""
        ...


class UserSessionRepository(Protocol):
    def create(self, session: UserSession) -> UserSession: ...

    def get_by_id(self, session_id: uuid.UUID) -> UserSession | None: ...

    def get_by_refresh_token_hash(self, token_hash: str) -> UserSession | None: ...

    def list_active_for_user(self, user_id: uuid.UUID) -> list[UserSession]: ...

    def revoke(self, session_id: uuid.UUID) -> None: ...

    def revoke_all_for_user(self, user_id: uuid.UUID) -> None: ...

    def touch_last_activity(self, session_id: uuid.UUID) -> None: ...

    def is_token_reuse(self, token_hash: str) -> tuple[uuid.UUID, uuid.UUID] | None:
        """Added to close a real defect: this capability already existed on `DjangoUserSessionRepository` but was never part of the Application-facing Port, so `RefreshToken.execute()` had no Clean-Architecture-compliant way to call it. Returns `(user_id, session_id)` -- the identity `report_reuse()` needs to correctly revoke only the compromised user's own session family -- never the raw `RevokedTokenRecord` ORM row, which must not cross the Infrastructure/Application boundary."""
        ...


class RoleRepository(Protocol):
    def get_by_code(self, code: str) -> Role | None: ...

    def get_by_id(self, role_id: uuid.UUID) -> Role | None: ...

    def list_all(self) -> list[Role]: ...


class PermissionRepository(Protocol):
    def get_by_code(self, code: str) -> Permission | None: ...

    def list_permission_codes_for_role(self, role_id: uuid.UUID) -> list[str]: ...

    def set_permissions_for_role(self, role_id: uuid.UUID, codes: set[str]) -> tuple[list[str], list[str]]: ...


class RoleAssignmentRepository(Protocol):
    def assign(self, assignment: RoleAssignment) -> RoleAssignment: ...

    def exists(self, user_id: uuid.UUID, role_id: uuid.UUID, store_id: uuid.UUID | None) -> bool: ...

    def list_effective_permission_codes(self, user_id: uuid.UUID, store_id: uuid.UUID | None = None) -> set[str]: ...

    def list_role_codes_for_user(self, user_id: uuid.UUID) -> list[str]: ...

    def list_store_ids_for_user(self, user_id: uuid.UUID) -> set[uuid.UUID]: ...

    def remove(self, assignment_id: uuid.UUID) -> dict | None: ...


class AvatarAssetRepository(Protocol):
    """Backs `identity.UserAvatarAsset` -- see that model's docstring for why avatar storage is temporarily owned by `identity`."""

    def create(
        self,
        user_id: uuid.UUID,
        storage_path: str,
        webp_path: str | None,
        thumbnail_paths: dict[str, str],
        width_px: int | None,
        height_px: int | None,
        checksum_sha256: str,
    ) -> uuid.UUID:
        """Returns the new asset's id."""
        ...


class OTPProviderError(Exception):
    """
    Shared base for any exception a conforming `OTPProvider` adapter
    may raise -- part of this port's own contract, not a
    provider-specific implementation detail. `ConsoleOTPProvider`
    never raises; `EskizOTPProvider`'s own `OTPProviderNonRetryableError`/
    `OTPProviderConfigurationError` (infrastructure/gateways/
    otp_providers.py) both subclass this. Lets Application-layer
    callers (`RequestOTP`) catch this one, narrow, port-level type
    rather than either a specific provider's own exception classes
    (which would leak implementation detail into Application) or a
    bare `Exception` (which would also mask genuine programming bugs).
    """


class OTPProvider(Protocol):
    """
    The Anti-Corruption Layer boundary for SMS delivery (Domain
    Architecture Specification §5). Concrete adapters (Eskiz,
    PlayMobile, Twilio) live in `infrastructure/gateways/otp_providers.py`
    and implement this interface -- no provider-specific type or
    response shape is ever allowed past this boundary into
    `application/`.
    """

    def send_otp(self, phone_number: PhoneNumber, code: str) -> bool:
        """Returns True if the provider accepted the message for delivery."""
        ...


class SocialAuthProvider(Protocol):
    """
    Provider-pattern seam for Google/Telegram login (mission: "prepare
    architecture... do not implement external API calls yet"). Concrete
    adapters are added in `infrastructure/gateways/social_auth.py` when
    those integrations are actually built.
    """

    def verify_and_get_external_id(self, credential: str) -> str:
        """Returns the provider's stable external user id, or raises AuthenticationRequired-family exception on invalid credential."""
        ...


class IssuedTokenPair(Protocol):
    """Structural shape returned by TokenIssuer.issue() -- see application/services/auth.py's local dataclass for the concrete DTO."""

    access_token: str
    refresh_token: str
    refresh_token_hash: str
    refresh_expires_at: datetime


class TokenIssuer(Protocol):
    """
    Wraps JWT issuance (djangorestframework-simplejwt, per Enterprise
    REST API Blueprint §4) behind an interface so `application/`
    depends on this Protocol, never on `rest_framework_simplejwt`
    directly -- the concrete implementation
    (infrastructure/security.py) is where that third-party dependency
    is allowed to appear.
    """

    def issue(self, user_id: uuid.UUID) -> IssuedTokenPair: ...

    def blacklist_refresh_token(self, raw_refresh_token: str) -> None: ...

    def hash_refresh_token(self, raw_refresh_token: str) -> str: ...
