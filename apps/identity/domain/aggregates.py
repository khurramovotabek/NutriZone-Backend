"""
Identity aggregate roots: User and Role.

Per Domain Architecture Specification §2.1:
  - User (root) owns AuthMethods, Sessions, Devices, Role assignment.
  - Role (root) owns its Permission set.

All state-changing methods here enforce the aggregate's own invariants
and return the domain events the change should raise (per MIC §7's
"Commands vs Queries" rule -- a Command may emit events, and here it
does so by returning them for the calling Application Service to stage
via the Outbox, rather than the aggregate reaching into infrastructure
itself, which would violate the "domain has zero Django imports" rule).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from apps.identity.domain.enums import FitnessGoal, LanguagePreference, UserStatus
from apps.identity.domain.events import UserBlocked, UserProfileUpdated, UserRoleAssigned
from apps.identity.domain.exceptions import (
    AccountBlockedError,
    InvalidProfileTransitionError,
)
from apps.identity.domain.value_objects import Email, FitnessProfile, PhoneNumber


class _Unset:
    """
    A real PATCH-semantics defect fix: `update_profile()` previously
    treated `None` as "field not supplied," which made it structurally
    impossible for an API client to ever explicitly clear a nullable
    field -- even though `UpdateProfileSerializer` already declares
    `allow_null=True` on `email`/`username`/`bio`/`birthday`/
    `height_cm`/`weight_kg`/`goal`, direct evidence the API contract
    already intended clearing to be possible. `UNSET` (the sentinel
    instance below) now means "not supplied, leave unchanged";
    `None` now genuinely means "clear this field."
    """

    def __repr__(self) -> str:  # pragma: no cover
        return "UNSET"


UNSET = _Unset()


@dataclass(slots=True)
class User:
    """
    The Identity aggregate root.

    Required fields per the mission's User Entity spec: id,
    phone_number, email (nullable), telegram_username (nullable),
    full_name, username (nullable), profile_picture (nullable, a
    content.media_library id reference -- cross-schema, no FK, per
    Database Blueprint §1.2), bio (nullable), birthday (nullable),
    fitness profile (height/weight/goal, nullable), language
    preference, status.
    """

    id: uuid.UUID
    phone_number: PhoneNumber
    full_name: str
    status: UserStatus = UserStatus.PENDING_VERIFICATION
    email: Email | None = None
    telegram_username: str | None = None
    username: str | None = None
    profile_picture_media_id: uuid.UUID | None = None
    bio: str | None = None
    birthday: date | None = None
    fitness_profile: FitnessProfile = field(default_factory=FitnessProfile)
    language: LanguagePreference = LanguagePreference.EN
    created_at: datetime | None = None

    # --- Invariant-enforcing state transitions ---

    def activate(self) -> None:
        if self.status == UserStatus.BLOCKED:
            raise InvalidProfileTransitionError("A blocked account cannot be activated directly; unblock it first.")
        self.status = UserStatus.ACTIVE

    def block(self, reason: str | None = None) -> UserBlocked:
        if self.status == UserStatus.BLOCKED:
            raise InvalidProfileTransitionError("This account is already blocked.")
        self.status = UserStatus.BLOCKED
        return UserBlocked(user_id=self.id, reason=reason)

    def unblock(self) -> None:
        if self.status != UserStatus.BLOCKED:
            raise InvalidProfileTransitionError("This account is not currently blocked.")
        self.status = UserStatus.ACTIVE

    def assert_can_authenticate(self) -> None:
        """Raised by VerifyOTP/RefreshToken before issuing tokens -- the one place account status gates authentication."""
        if self.status == UserStatus.BLOCKED:
            raise AccountBlockedError("This account has been blocked.")

    def update_profile(
        self,
        full_name: str | None = None,
        email: Email | None | _Unset = UNSET,
        username: str | None | _Unset = UNSET,
        bio: str | None | _Unset = UNSET,
        birthday: date | None | _Unset = UNSET,
        fitness_profile: FitnessProfile | None = None,
        language: LanguagePreference | None = None,
    ) -> UserProfileUpdated:
        """
        A real PATCH-semantics defect fixed here: `email`/`username`/
        `bio`/`birthday` now default to `UNSET` (leave unchanged),
        with `None` genuinely meaning "clear this field" -- matching
        `UpdateProfileSerializer`'s own `allow_null=True` declarations,
        which already promised this capability at the API boundary.
        `full_name` (non-nullable) and `fitness_profile`/`language`
        (already handled as whole-value replacements by the caller)
        correctly keep their original `None`-means-"not supplied"
        semantics -- there is no valid "clear" state for a required
        field, and the fitness/language merge logic already lives at
        the Application layer, one level up.
        """
        before = self._snapshot()

        if full_name is not None:
            self.full_name = full_name
        if email is not UNSET:
            self.email = email
        if username is not UNSET:
            self.username = username
        if bio is not UNSET:
            self.bio = bio
        if birthday is not UNSET:
            self.birthday = birthday
        if fitness_profile is not None:
            self.fitness_profile = fitness_profile
        if language is not None:
            self.language = language

        after = self._snapshot()
        return UserProfileUpdated(user_id=self.id, before=before, after=after)

    def set_avatar(self, media_id: uuid.UUID) -> None:
        self.profile_picture_media_id = media_id

    def _snapshot(self) -> dict:
        return {
            "full_name": self.full_name,
            "email": str(self.email) if self.email else None,
            "username": self.username,
            "bio": self.bio,
            "birthday": self.birthday.isoformat() if self.birthday else None,
            "language": self.language.value,
        }


@dataclass(slots=True)
class Role:
    """The Role aggregate root -- owns its Permission set via RolePermission (application/repository-managed, not held in memory here to avoid loading every permission for every role read)."""

    id: uuid.UUID
    code: str
    name: str
    is_system_role: bool = False

    def assign_to(self, user_id: uuid.UUID, store_id: uuid.UUID | None = None) -> UserRoleAssigned:
        return UserRoleAssigned(user_id=user_id, role_id=self.id, role_code=self.code, store_id=store_id)
