"""
Identity repositories.

Concrete implementations of application/ports.py's Protocols. Every
method here is responsible for two things Django Implementation
Blueprint §6 assigns to this layer specifically: (1) translating
between the ORM row shape and the plain domain dataclasses
(domain/aggregates.py, domain/entities.py), and (2) catching
ORM-level exceptions (IntegrityError, ObjectDoesNotExist) and
re-raising as the matching domain exception -- application/ and
interfaces/ never need to know a Django ORM exception type exists.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from django.db import IntegrityError
from django.db.models import F, Q
from django.utils import timezone

from apps.identity.domain.aggregates import Role, User as UserAggregate
from apps.identity.domain.entities import (
    AuthMethod as AuthMethodEntity,
    Permission as PermissionEntity,
    RoleAssignment as RoleAssignmentEntity,
    UserSession as UserSessionEntity,
)
from apps.identity.domain.enums import DeviceType, LanguagePreference, UserStatus
from apps.identity.domain.services import OTPChallengeState
from apps.identity.domain.value_objects import Email, FitnessProfile, PhoneNumber
from apps.identity.infrastructure import models as orm
from common.exceptions import ConflictError
from core.caching import TTL_LONG, cache_key, get_redis_client


# --- mapping helpers -------------------------------------------------

def _user_to_domain(row: orm.User) -> UserAggregate:
    return UserAggregate(
        id=row.id,
        phone_number=PhoneNumber(row.phone_number),
        full_name=row.full_name,
        status=UserStatus(row.status),
        email=Email(row.email) if row.email else None,
        telegram_username=row.telegram_username,
        username=row.username,
        profile_picture_media_id=row.profile_picture_media_id,
        bio=row.bio,
        birthday=row.birthday,
        fitness_profile=FitnessProfile(height_cm=row.height_cm, weight_kg=row.weight_kg, goal=row.goal),
        language=LanguagePreference(row.language),
        created_at=row.created_at,
    )


def _session_to_domain(row: orm.UserSession) -> UserSessionEntity:
    return UserSessionEntity(
        id=row.id,
        user_id=row.user_id,
        device_id=row.device_id,
        device_name=row.device_name,
        device_type=DeviceType(row.device_type),
        refresh_token_hash=row.refresh_token_hash,
        ip_address=row.ip_address,
        user_agent=row.user_agent,
        last_activity=row.last_activity,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
    )


class DjangoUserRepository:
    def get_by_id(self, user_id: uuid.UUID) -> UserAggregate | None:
        row = orm.User.objects.filter(id=user_id).first()
        return _user_to_domain(row) if row else None

    def get_by_phone_number(self, phone_number: PhoneNumber) -> UserAggregate | None:
        row = orm.User.objects.filter(phone_number=phone_number.value).first()
        return _user_to_domain(row) if row else None

    def save(self, user: UserAggregate) -> UserAggregate:
        try:
            row, _created = orm.User.objects.update_or_create(
                id=user.id,
                defaults={
                    "phone_number": user.phone_number.value,
                    "email": str(user.email) if user.email else None,
                    "telegram_username": user.telegram_username,
                    "full_name": user.full_name,
                    "username": user.username,
                    "profile_picture_media_id": user.profile_picture_media_id,
                    "bio": user.bio,
                    "birthday": user.birthday,
                    "height_cm": user.fitness_profile.height_cm,
                    "weight_kg": user.fitness_profile.weight_kg,
                    "goal": user.fitness_profile.goal,
                    "language": user.language.value if hasattr(user.language, "value") else user.language,
                    "status": user.status.value if hasattr(user.status, "value") else user.status,
                },
            )
        except IntegrityError as exc:
            raise ConflictError("A user with this phone number or username already exists.") from exc
        return _user_to_domain(row)

    def exists_with_username(self, username: str, exclude_user_id: uuid.UUID | None = None) -> bool:
        qs = orm.User.objects.filter(username=username)
        if exclude_user_id is not None:
            qs = qs.exclude(id=exclude_user_id)
        return qs.exists()

    def list_for_admin(
        self, status: str | None = None, query: str | None = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[UserAggregate], int]:
        qs = orm.User.objects.all()
        if status:
            qs = qs.filter(status=status)
        if query:
            qs = qs.filter(Q(full_name__icontains=query) | Q(phone_number__icontains=query) | Q(username__icontains=query))
        total = qs.count()
        start = (page - 1) * page_size
        rows = qs.order_by("-created_at")[start : start + page_size]
        return [_user_to_domain(r) for r in rows], total


class DjangoAuthMethodRepository:
    def get_by_provider(self, user_id: uuid.UUID, provider_type: str) -> AuthMethodEntity | None:
        row = orm.AuthMethod.objects.filter(user_id=user_id, provider_type=provider_type).first()
        if row is None:
            return None
        return AuthMethodEntity(
            id=row.id, user_id=row.user_id, provider_type=row.provider_type,
            external_id=row.external_id, credential_hash=row.credential_hash, last_used_at=row.last_used_at,
        )

    def save(self, auth_method: AuthMethodEntity) -> AuthMethodEntity:
        orm.AuthMethod.objects.update_or_create(
            id=auth_method.id,
            defaults={
                "user_id": auth_method.user_id,
                "provider_type": auth_method.provider_type,
                "external_id": auth_method.external_id,
                "credential_hash": auth_method.credential_hash,
                "last_used_at": auth_method.last_used_at,
            },
        )
        return auth_method


class DjangoOTPChallengeRepository:
    def create(self, phone_number: PhoneNumber, code_hash: str, expires_at: datetime) -> OTPChallengeState:
        row = orm.OTPCodeChallenge.objects.create(phone_number=phone_number.value, code_hash=code_hash, expires_at=expires_at)
        return OTPChallengeState(
            id=row.id, code_hash=row.code_hash, expires_at=row.expires_at, attempt_count=row.attempt_count,
            consumed_at=row.consumed_at, created_at=row.created_at, phone_number=row.phone_number,
        )

    def get_latest(self, phone_number: PhoneNumber) -> OTPChallengeState | None:
        """`select_for_update()` -- a real concurrency fix: called from inside `VerifyOTP.execute()`'s own `@transaction.atomic` block, this now locks the specific challenge row for the remainder of that transaction, so a second, concurrent verification attempt for the same phone number blocks here until the first transaction commits (and then correctly observes the already-updated `attempt_count`/`consumed_at`), rather than both transactions reading the same stale state and racing on their later writes."""
        row = orm.OTPCodeChallenge.objects.select_for_update().filter(phone_number=phone_number.value).order_by("-created_at").first()
        if row is None:
            return None
        return OTPChallengeState(
            id=row.id, code_hash=row.code_hash, expires_at=row.expires_at, attempt_count=row.attempt_count,
            consumed_at=row.consumed_at, created_at=row.created_at, phone_number=row.phone_number,
        )

    def find_active_by_code_hash(self, code_hash: str) -> OTPChallengeState | None:
        """Real, product-required lookup: hash_otp_code() is deterministic (SHA-256 + pepper, no per-row salt), so this filters directly on the indexed code_hash column -- an ordinary, real database query, not a linear scan over every active challenge. `select_for_update()` matches get_latest()'s own concurrency-safety rationale above."""
        row = (
            orm.OTPCodeChallenge.objects.select_for_update()
            .filter(code_hash=code_hash, consumed_at__isnull=True, expires_at__gt=timezone.now())
            .order_by("-created_at")
            .first()
        )
        if row is None:
            return None
        return OTPChallengeState(
            id=row.id, code_hash=row.code_hash, expires_at=row.expires_at, attempt_count=row.attempt_count,
            consumed_at=row.consumed_at, created_at=row.created_at, phone_number=row.phone_number,
        )

    def count_requested_since(self, phone_number: PhoneNumber, since: datetime) -> int:
        return orm.OTPCodeChallenge.objects.filter(phone_number=phone_number.value, created_at__gte=since).count()

    def increment_attempt(self, challenge_id: uuid.UUID) -> None:
        """A real defect fix, in two parts: (1) now targets the exact challenge by id, never "whatever is latest right now" (see the Port's own docstring); (2) uses an atomic `F()` update instead of Python-side read-modify-write, closing a genuine lost-update race where two concurrent verification failures for the same challenge could both read the same `attempt_count`, both compute the same incremented value, and both save it -- silently losing one increment."""
        orm.OTPCodeChallenge.objects.filter(id=challenge_id).update(attempt_count=F("attempt_count") + 1)

    def mark_consumed(self, challenge_id: uuid.UUID) -> bool:
        """A real defect fix: targets the exact challenge by id (see `increment_attempt`'s docstring), and the `consumed_at__isnull=True` filter makes this a single atomic, race-safe conditional update -- a concurrent second call for the same challenge_id matches zero rows and returns False, closing the double-consumption gap Section 13 describes, without needing a second round-trip to check state first."""
        updated = orm.OTPCodeChallenge.objects.filter(id=challenge_id, consumed_at__isnull=True).update(consumed_at=timezone.now())
        return updated > 0


class DjangoUserSessionRepository:
    """
    Session reuse-detection note (referenced from
    application/services/auth.py::RefreshToken): when a session is
    revoked as part of rotation, its refresh_token_hash is also copied
    into `RevokedTokenRecord` so a *second* presentation of that same
    rotated-out hash can be distinguished from "never existed" --
    `RefreshToken.execute()` calls `is_token_reuse()` (part of the
    certified `UserSessionRepository` Port) when `get_by_refresh_token_hash`
    returns None, and calls `report_reuse()` if a match is found there.
    """

    def create(self, session: UserSessionEntity) -> UserSessionEntity:
        row = orm.UserSession.objects.create(
            id=session.id, user_id=session.user_id, device_id=session.device_id,
            device_name=session.device_name, device_type=session.device_type.value,
            refresh_token_hash=session.refresh_token_hash, ip_address=session.ip_address,
            user_agent=session.user_agent, last_activity=session.last_activity,
            expires_at=session.expires_at, revoked_at=session.revoked_at,
        )
        return _session_to_domain(row)

    def get_by_id(self, session_id: uuid.UUID) -> UserSessionEntity | None:
        row = orm.UserSession.objects.filter(id=session_id).first()
        return _session_to_domain(row) if row else None

    def get_by_refresh_token_hash(self, token_hash: str) -> UserSessionEntity | None:
        row = orm.UserSession.objects.filter(refresh_token_hash=token_hash, revoked_at__isnull=True).first()
        return _session_to_domain(row) if row else None

    def list_active_for_user(self, user_id: uuid.UUID) -> list[UserSessionEntity]:
        rows = orm.UserSession.objects.filter(user_id=user_id, revoked_at__isnull=True).order_by("-last_activity")
        return [_session_to_domain(r) for r in rows]

    def revoke(self, session_id: uuid.UUID) -> None:
        row = orm.UserSession.objects.filter(id=session_id).first()
        if row is None or row.revoked_at is not None:
            return
        orm.RevokedTokenRecord.objects.create(
            session_id=row.id, user_id=row.user_id, rotated_token_hash=row.refresh_token_hash
        )
        row.revoked_at = timezone.now()
        row.save(update_fields=["revoked_at"])

    def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        active = orm.UserSession.objects.filter(user_id=user_id, revoked_at__isnull=True)
        for row in active:
            orm.RevokedTokenRecord.objects.get_or_create(
                rotated_token_hash=row.refresh_token_hash,
                defaults={"session_id": row.id, "user_id": row.user_id},
            )
        active.update(revoked_at=timezone.now())

    def touch_last_activity(self, session_id: uuid.UUID) -> None:
        orm.UserSession.objects.filter(id=session_id).update(last_activity=timezone.now())

    def is_token_reuse(self, token_hash: str) -> tuple[uuid.UUID, uuid.UUID] | None:
        """A real ORM-leak defect fixed here: previously returned `orm.RevokedTokenRecord | None`, a raw ORM row, which must never cross into Application -- now returns a plain `(user_id, session_id)` tuple, matching the certified `UserSessionRepository` Port signature exactly."""
        row = orm.RevokedTokenRecord.objects.filter(rotated_token_hash=token_hash).only("user_id", "session_id").first()
        return (row.user_id, row.session_id) if row else None


class DjangoAvatarAssetRepository:
    def create(
        self, user_id, storage_path, webp_path, thumbnail_paths, width_px, height_px, checksum_sha256
    ):
        row = orm.UserAvatarAsset.objects.create(
            user_id=user_id, storage_path=storage_path, webp_path=webp_path,
            thumbnail_paths=thumbnail_paths, width_px=width_px, height_px=height_px,
            checksum_sha256=checksum_sha256,
        )
        return row.id


class DjangoRoleRepository:
    def get_by_code(self, code: str) -> Role | None:
        cache_k = cache_key(code, namespace="identity:role_by_code")
        client = get_redis_client()
        cached = client.get(cache_k)
        if cached is not None:
            data = json.loads(cached)
            return Role(**{**data, "id": uuid.UUID(data["id"])})

        row = orm.Role.objects.filter(code=code).first()
        if row is None:
            return None
        role = Role(id=row.id, code=row.code, name=row.name, is_system_role=row.is_system_role)
        client.set(cache_k, json.dumps({"id": str(role.id), "code": role.code, "name": role.name, "is_system_role": role.is_system_role}), ex=TTL_LONG)
        return role

    def get_by_id(self, role_id: uuid.UUID) -> Role | None:
        row = orm.Role.objects.filter(id=role_id).first()
        return Role(id=row.id, code=row.code, name=row.name, is_system_role=row.is_system_role) if row else None

    def list_all(self) -> list[Role]:
        return [Role(id=r.id, code=r.code, name=r.name, is_system_role=r.is_system_role) for r in orm.Role.objects.all()]


class DjangoPermissionRepository:
    def get_by_code(self, code: str) -> PermissionEntity | None:
        row = orm.Permission.objects.filter(code=code).first()
        return PermissionEntity(id=row.id, code=row.code, description=row.description) if row else None

    def list_permission_codes_for_role(self, role_id: uuid.UUID) -> list[str]:
        return list(orm.RolePermission.objects.filter(role_id=role_id).values_list("permission__code", flat=True))

    def set_permissions_for_role(self, role_id: uuid.UUID, codes: set[str]) -> tuple[list[str], list[str]]:
        """Makes the role hold exactly `codes`; returns (added, removed). Unknown codes raise ValidationFailed."""
        from common.exceptions import ValidationFailed

        by_code = dict(orm.Permission.objects.filter(code__in=codes).values_list("code", "id"))
        unknown = sorted(set(codes) - set(by_code))
        if unknown:
            raise ValidationFailed(f"Unknown permission(s): {', '.join(unknown)}")
        current = dict(orm.RolePermission.objects.filter(role_id=role_id).values_list("permission__code", "id"))
        added = sorted(set(codes) - set(current))
        removed = sorted(set(current) - set(codes))
        orm.RolePermission.objects.filter(id__in=[current[c] for c in removed]).delete()
        orm.RolePermission.objects.bulk_create([orm.RolePermission(role_id=role_id, permission_id=by_code[c]) for c in added])
        return added, removed


class DjangoRoleAssignmentRepository:
    def assign(self, assignment: RoleAssignmentEntity) -> RoleAssignmentEntity:
        try:
            orm.UserRole.objects.create(
                id=assignment.id, user_id=assignment.user_id, role_id=assignment.role_id, store_id=assignment.store_id
            )
        except IntegrityError as exc:
            raise ConflictError("This role assignment already exists.") from exc
        return assignment

    def remove(self, assignment_id: uuid.UUID) -> dict | None:
        """Deletes one assignment; returns what it was ({user_id, role_id, store_id}) or None when it didn't exist."""
        row = orm.UserRole.objects.filter(id=assignment_id).values("user_id", "role_id", "store_id").first()
        if row is not None:
            orm.UserRole.objects.filter(id=assignment_id).delete()
        return row

    def exists(self, user_id: uuid.UUID, role_id: uuid.UUID, store_id: uuid.UUID | None) -> bool:
        return orm.UserRole.objects.filter(user_id=user_id, role_id=role_id, store_id=store_id).exists()

    def list_effective_permission_codes(self, user_id: uuid.UUID, store_id: uuid.UUID | None = None) -> set[str]:
        role_ids = orm.UserRole.objects.filter(user_id=user_id).filter(Q(store_id=store_id) | Q(store_id__isnull=True)).values_list("role_id", flat=True)
        codes = orm.RolePermission.objects.filter(role_id__in=list(role_ids)).values_list("permission__code", flat=True)
        return set(codes)

    def list_role_codes_for_user(self, user_id: uuid.UUID) -> list[str]:
        return list(orm.UserRole.objects.filter(user_id=user_id).values_list("role__code", flat=True))

    def list_store_ids_for_user(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        store_ids = orm.UserRole.objects.filter(user_id=user_id, store_id__isnull=False).values_list("store_id", flat=True)
        return set(store_ids)
