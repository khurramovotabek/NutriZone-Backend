"""
Profile-management application services: GetOwnProfile, UpdateProfile,
SetAvatar, UploadAvatar.

Caching (this phase's mission §10): the current-profile read is
Redis-cached (short TTL, invalidated explicitly on every write in this
module) -- deliberately NOT using `core.caching.CacheManager`/
`CacheDomain`, since "profile" is not one of that mechanism's five
fixed business-cache domains (product/search/store/wallet/analytics)
from the prior Foundation Hardening phase; this module talks to Redis
directly via the same low-level `cache_key()`/`get_redis_client()`
primitives `CheckPermission` (roles.py) already uses for the identical
reason. OTP challenges and session data are never cached, per the
mission's explicit "never cache: OTP, Sessions, Security information"
rule -- there is no code path in this file that writes OTP/session
data to Redis.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from types import SimpleNamespace

from django.db import transaction

from apps.identity.application.ports import UserRepository
from apps.identity.domain.aggregates import UNSET, _Unset
from apps.identity.domain.enums import LanguagePreference
from apps.identity.domain.value_objects import Email, FitnessProfile
from common.exceptions import ConflictError, ResourceNotFound
from core.audit import AuditEventBuilder
from core.caching import TTL_SHORT, cache_key, get_redis_client

_PROFILE_CACHE_NAMESPACE = "identity:profile"


def _profile_cache_key(user_id: uuid.UUID) -> str:
    return cache_key(user_id, namespace=_PROFILE_CACHE_NAMESPACE)


def _invalidate_profile_cache(user_id: uuid.UUID) -> None:
    get_redis_client().delete(_profile_cache_key(user_id))


def _user_to_cache_dict(user) -> dict:
    return {
        "id": str(user.id),
        "phone_number": user.phone_number.value,
        "email": str(user.email) if user.email else None,
        "telegram_username": user.telegram_username,
        "full_name": user.full_name,
        "username": user.username,
        "profile_picture_media_id": str(user.profile_picture_media_id) if user.profile_picture_media_id else None,
        "bio": user.bio,
        "birthday": user.birthday.isoformat() if user.birthday else None,
        "height_cm": user.fitness_profile.height_cm,
        "weight_kg": user.fitness_profile.weight_kg,
        "goal": user.fitness_profile.goal,
        "language": user.language.value if hasattr(user.language, "value") else user.language,
        "status": user.status.value if hasattr(user.status, "value") else user.status,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": None,
        "version": None,
    }


def _cache_dict_to_namespace(data: dict) -> SimpleNamespace:
    """Reconstructs an object exposing the same attribute paths UserProfileSerializer reads (including the nested `fitness_profile.*` source paths) from a cached plain dict."""
    return SimpleNamespace(
        id=data["id"], phone_number=data["phone_number"], email=data["email"],
        telegram_username=data["telegram_username"], full_name=data["full_name"], username=data["username"],
        profile_picture_media_id=data["profile_picture_media_id"], bio=data["bio"], birthday=data["birthday"],
        fitness_profile=SimpleNamespace(height_cm=data["height_cm"], weight_kg=data["weight_kg"], goal=data["goal"]),
        language=data["language"], status=data["status"], created_at=data["created_at"],
        updated_at=data["updated_at"], version=data["version"],
    )


class GetOwnProfile:
    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    def execute(self, user_id: uuid.UUID):
        from common.exceptions import ResourceNotFound

        cached = get_redis_client().get(_profile_cache_key(user_id))
        if cached is not None:
            return _cache_dict_to_namespace(json.loads(cached))

        user = self._user_repo.get_by_id(user_id)
        if user is None:
            raise ResourceNotFound("User not found.")

        get_redis_client().set(_profile_cache_key(user_id), json.dumps(_user_to_cache_dict(user)), ex=TTL_SHORT)
        return user


class UpdateProfile:
    def __init__(self, user_repo: UserRepository, stage_events) -> None:
        self._user_repo = user_repo
        self._stage_events = stage_events

    @transaction.atomic
    def execute(
        self,
        user_id: uuid.UUID,
        full_name: str | None = None,
        email: str | None | _Unset = UNSET,
        username: str | None | _Unset = UNSET,
        bio: str | None | _Unset = UNSET,
        birthday: date | None | _Unset = UNSET,
        height_cm: float | None | _Unset = UNSET,
        weight_kg: float | None | _Unset = UNSET,
        goal: str | None | _Unset = UNSET,
        language: str | None = None,
    ):
        """
        A real PATCH-semantics defect fixed here, at both this layer
        and the Domain layer it calls into (`User.update_profile()`):
        `email`/`username`/`bio`/`birthday`/`height_cm`/`weight_kg`/
        `goal` now default to `UNSET` (leave unchanged) rather than
        `None`, with `None` genuinely meaning "clear this field" --
        matching `UpdateProfileSerializer`'s own `allow_null=True`
        declarations on exactly these seven fields, which already
        promised this capability. The fitness-profile composite
        previously had the identical bug: supplying `height_cm=None`
        to clear it was indistinguishable from not supplying it at
        all.
        """
        user = self._user_repo.get_by_id(user_id)
        if user is None:
            raise ResourceNotFound("User not found.")

        if username not in (UNSET, None) and self._user_repo.exists_with_username(username, exclude_user_id=user_id):
            raise ConflictError("This username is already taken.", details={"fields": [{"field": "username", "code": "ALREADY_TAKEN"}]})

        fitness_profile = None
        if height_cm is not UNSET or weight_kg is not UNSET or goal is not UNSET:
            base = user.fitness_profile
            fitness_profile = FitnessProfile(
                height_cm=height_cm if height_cm is not UNSET else base.height_cm,
                weight_kg=weight_kg if weight_kg is not UNSET else base.weight_kg,
                goal=goal if goal is not UNSET else base.goal,
            )

        event = user.update_profile(
            full_name=full_name,
            email=(Email(email) if email not in (UNSET, None) else email),
            username=username,
            bio=bio,
            birthday=birthday,
            fitness_profile=fitness_profile,
            language=LanguagePreference(language) if language is not None else None,
        )
        saved = self._user_repo.save(user)
        self._stage_events([("UserProfileUpdated", event.to_payload())])
        _invalidate_profile_cache(user_id)

        audit = AuditEventBuilder(context_schema="identity", actor_id=str(user_id))
        audit.updated(entity_type="User", entity_id=str(user_id), before=event.before, after=event.after)

        return saved


class SetAvatar:
    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    @transaction.atomic
    def execute(self, user_id: uuid.UUID, media_id: uuid.UUID):
        from common.exceptions import ResourceNotFound

        user = self._user_repo.get_by_id(user_id)
        if user is None:
            raise ResourceNotFound("User not found.")
        user.set_avatar(media_id)
        saved = self._user_repo.save(user)
        _invalidate_profile_cache(user_id)
        return saved


class UploadAvatar:
    """
    Runs an uploaded avatar image through `core.media.MediaPipeline`
    (validate -> scan -> optimize -> WebP -> thumbnails -> store),
    persists the result as a `UserAvatarAsset`, and points the User
    aggregate's `profile_picture_media_id` at the new asset.
    """

    def __init__(self, user_repo: UserRepository, avatar_repo, media_pipeline, stage_events) -> None:
        self._user_repo = user_repo
        self._avatar_repo = avatar_repo
        self._media_pipeline = media_pipeline
        self._stage_events = stage_events

    @transaction.atomic
    def execute(self, user_id: uuid.UUID, filename: str, content: bytes, mime_type: str):
        from common.exceptions import ResourceNotFound, ValidationFailed
        from core.media import MediaType, MediaUploadRequest

        user = self._user_repo.get_by_id(user_id)
        if user is None:
            raise ResourceNotFound("User not found.")

        request = MediaUploadRequest(filename=filename, content=content, mime_type=mime_type, media_type=MediaType.IMAGE)
        result = self._media_pipeline.process(request)
        if result.is_failure:
            first_error = result.errors[0]
            raise ValidationFailed(first_error.message, details={"fields": [{"field": "avatar", "code": first_error.code}]})

        processed = result.value
        webp_path = None
        if processed.has_webp_variant:
            from core.media import build_storage_path

            webp_path = build_storage_path(processed.media_type, processed.metadata.checksum_sha256, "webp")

        asset_id = self._avatar_repo.create(
            user_id=user_id,
            storage_path=processed.storage_path,
            webp_path=webp_path,
            thumbnail_paths=processed.thumbnail_paths,
            width_px=processed.metadata.width_px,
            height_px=processed.metadata.height_px,
            checksum_sha256=processed.metadata.checksum_sha256,
        )

        before = {"profile_picture_media_id": str(user.profile_picture_media_id) if user.profile_picture_media_id else None}
        user.set_avatar(asset_id)
        saved = self._user_repo.save(user)
        _invalidate_profile_cache(user_id)

        audit = AuditEventBuilder(context_schema="identity", actor_id=str(user_id))
        audit.updated(entity_type="User", entity_id=str(user_id), before=before, after={"profile_picture_media_id": str(asset_id)})

        self._stage_events([("UserProfileUpdated", {"user_id": str(user_id), "before": before, "after": {"profile_picture_media_id": str(asset_id)}})])

        return saved, processed
