"""
Identity API serializers.

Structural validation only (Django Implementation Blueprint §6's
400-vs-422 split) -- format checks call the same domain value objects
used elsewhere (PhoneNumber, OTPCode) rather than re-implementing
regexes, per MIC §6's "a business rule is implemented in exactly one
place" rule. Business validation (OTP expiry, quota, uniqueness) is
never duplicated here; it's surfaced automatically as a 422 when the
Application Service raises.
"""
from __future__ import annotations

from rest_framework import serializers

from apps.identity.domain.enums import FitnessGoal, LanguagePreference, UserStatus
from apps.identity.domain.value_objects import OTPCode, PhoneNumber
from common.exceptions import ValidationFailed
from common.serializers import ReadOnlyAuditFieldsMixin


class RequestOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField()

    def validate_phone_number(self, value: str) -> str:
        try:
            PhoneNumber(value)
        except ValidationFailed as exc:
            raise serializers.ValidationError(exc.message) from exc
        return value


class VerifyOTPSerializer(serializers.Serializer):
    phone_number = serializers.CharField()
    code = serializers.CharField()

    def validate_phone_number(self, value: str) -> str:
        try:
            PhoneNumber(value)
        except ValidationFailed as exc:
            raise serializers.ValidationError(exc.message) from exc
        return value

    def validate_code(self, value: str) -> str:
        try:
            OTPCode(value)
        except ValidationFailed as exc:
            raise serializers.ValidationError(exc.message) from exc
        return value


class VerifyCodeOnlySerializer(serializers.Serializer):
    """
    Real, product-required serializer: the website's own login page
    never collects a phone number at all -- the user gets their
    6-digit code from the Telegram bot (which already knows their
    phone number) and types only the code here.
    """

    code = serializers.CharField()

    def validate_code(self, value: str) -> str:
        try:
            OTPCode(value)
        except ValidationFailed as exc:
            raise serializers.ValidationError(exc.message) from exc
        return value


class RefreshTokenSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField(required=False, allow_blank=True)


class TokenPairResponseSerializer(serializers.Serializer):
    """Response-only shape (REST API Blueprint §6's success envelope wraps this in `data`)."""

    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    session_id = serializers.UUIDField()
    is_new_user = serializers.BooleanField()


class FitnessProfileSerializer(serializers.Serializer):
    height_cm = serializers.FloatField(required=False, allow_null=True, min_value=30, max_value=300)
    weight_kg = serializers.FloatField(required=False, allow_null=True, min_value=10, max_value=500)
    goal = serializers.ChoiceField(choices=FitnessGoal.values(), required=False, allow_null=True)


class UserProfileSerializer(ReadOnlyAuditFieldsMixin, serializers.Serializer):
    """GET /identity/users/me response shape."""

    phone_number = serializers.CharField(read_only=True)
    email = serializers.CharField(read_only=True, allow_null=True)
    telegram_username = serializers.CharField(read_only=True, allow_null=True)
    full_name = serializers.CharField(read_only=True)
    username = serializers.CharField(read_only=True, allow_null=True)
    profile_picture_media_id = serializers.UUIDField(read_only=True, allow_null=True)
    avatar_url = serializers.SerializerMethodField()
    bio = serializers.CharField(read_only=True, allow_null=True)
    birthday = serializers.DateField(read_only=True, allow_null=True)
    height_cm = serializers.FloatField(read_only=True, allow_null=True, source="fitness_profile.height_cm")
    weight_kg = serializers.FloatField(read_only=True, allow_null=True, source="fitness_profile.weight_kg")
    goal = serializers.CharField(read_only=True, allow_null=True, source="fitness_profile.goal")
    language = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    telegram_connected = serializers.SerializerMethodField()

    def get_telegram_connected(self, obj) -> bool:
        """Whether the bot can DM this customer (Telegram notifications need `telegram_user_id`, which isn't on the domain User)."""
        from apps.identity.infrastructure.models import User as UserModel

        return UserModel.objects.filter(id=obj.id, telegram_user_id__isnull=False).exists()

    def get_avatar_url(self, obj) -> str | None:
        """Real, closed gap: profile_picture_media_id alone gives the frontend no usable image URL. Resolves the user's own most recent UserAvatarAsset (apps.identity.infrastructure.models -- the real, FK-backed owner of avatar assets, confirmed and used already in this build's admin UserAdmin.avatar_preview) and returns its "small" thumbnail path as a full, absolute-from-MEDIA_URL path. A single extra query per profile view -- never a per-row N+1, since this serializer is only ever used for one user at a time (GET/PATCH /users/me, avatar upload response)."""
        from django.conf import settings

        from apps.identity.infrastructure.models import UserAvatarAsset

        asset = UserAvatarAsset.objects.filter(user_id=obj.id).order_by("-created_at").first()
        if asset is None:
            return None
        path = asset.thumbnail_paths.get("small") or asset.storage_path
        base = (getattr(settings, "PUBLIC_BASE_URL", None) or "").rstrip("/")
        return path if path.startswith(("http://", "https://")) else f"{base}{settings.MEDIA_URL}{path}"


class UpdateProfileSerializer(serializers.Serializer):
    """PATCH /identity/users/me request shape -- every field optional (PATCH semantics)."""

    full_name = serializers.CharField(required=False, max_length=255)
    email = serializers.EmailField(required=False, allow_null=True)
    username = serializers.CharField(required=False, allow_null=True, max_length=64)
    bio = serializers.CharField(required=False, allow_null=True, max_length=2000)
    birthday = serializers.DateField(required=False, allow_null=True)
    height_cm = serializers.FloatField(required=False, allow_null=True, min_value=30, max_value=300)
    weight_kg = serializers.FloatField(required=False, allow_null=True, min_value=10, max_value=500)
    goal = serializers.ChoiceField(choices=FitnessGoal.values(), required=False, allow_null=True)
    language = serializers.ChoiceField(choices=LanguagePreference.values(), required=False)


class AvatarUploadSerializer(serializers.Serializer):
    media_id = serializers.UUIDField()


class UserSessionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    device_name = serializers.CharField(allow_null=True)
    device_type = serializers.CharField()
    ip_address = serializers.CharField(allow_null=True)
    last_activity = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    is_active = serializers.BooleanField()


class AdminUserListItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    phone_number = serializers.CharField()
    full_name = serializers.CharField()
    status = serializers.CharField()
    language = serializers.CharField()
    created_at = serializers.DateTimeField()


class AdminUserDetailSerializer(UserProfileSerializer):
    """Same shape as the self-service profile, exposed to staff with `identity.user.view`."""


class AdminUpdateUserStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=UserStatus.values())
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
