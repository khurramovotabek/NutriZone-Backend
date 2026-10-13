"""
Identity ORM models.

Maps 1:1 onto Enterprise Database Blueprint §4.1 (`identity` schema).
Every model composes from exactly one of common/models/'s three base
mixins per the model-category decision tree in the Universal Module
Implementation Contract §3. No business logic lives here (Django
Implementation Blueprint §4) -- these are pure persistence shapes;
`infrastructure/repositories.py` is the only code that constructs or
reads them on behalf of `application/`.
"""
from __future__ import annotations

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.identity.domain.enums import (
    AuthProviderType,
    DeviceType,
    FitnessGoal,
    LanguagePreference,
    UserStatus,
)
from common.models import AllObjectsManager, AppendOnlyModel, BaseModel, SoftDeleteModel
from common.utils import enum_field_kwargs
from core.outbox import AbstractOutboxEvent


class User(SoftDeleteModel):
    """Database Blueprint §4.1 `identity.users` -- soft-delete only, never hard-deleted (data-subject deletion is handled via anonymization, not row removal)."""

    phone_number = models.CharField(max_length=20, unique=True, db_index=True)
    email = models.CharField(max_length=254, null=True, blank=True)
    telegram_username = models.CharField(max_length=64, null=True, blank=True)
    telegram_user_id = models.BigIntegerField(null=True, blank=True, unique=True)  # Phase 15B: the stable identity resolver -- unlike telegram_username, this cannot change or be cleared by the user
    telegram_linked_at = models.DateTimeField(null=True, blank=True)
    telegram_cart_id = models.UUIDField(null=True, blank=True)  # Phase 15C: mirrors the web storefront's own HttpOnly cart-code cookie -- Cart has no reliable customer_id (token-ownership only, confirmed Phase 09.2), so this is the only way to remember "which cart belongs to this Telegram session" across stateless webhook requests
    telegram_cart_token = models.UUIDField(null=True, blank=True)
    full_name = models.CharField(max_length=255, blank=True)
    username = models.CharField(max_length=64, null=True, blank=True, unique=True)
    profile_picture_media_id = models.UUIDField(null=True, blank=True)  # cross-schema ref to content.media_library, no FK
    bio = models.TextField(null=True, blank=True)
    birthday = models.DateField(null=True, blank=True)

    height_cm = models.FloatField(null=True, blank=True)
    weight_kg = models.FloatField(null=True, blank=True)
    goal = models.CharField(null=True, blank=True, **enum_field_kwargs(FitnessGoal))

    language = models.CharField(default=LanguagePreference.EN.value, **enum_field_kwargs(LanguagePreference))
    status = models.CharField(default=UserStatus.PENDING_VERIFICATION.value, **enum_field_kwargs(UserStatus))

    class Meta:
        db_table = "identity_users"
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["phone_number"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return self.full_name or self.phone_number


class AuthMethod(BaseModel):
    """Database Blueprint §4.1 `identity.auth_methods`."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="auth_methods")
    provider_type = models.CharField(**enum_field_kwargs(AuthProviderType))
    external_id = models.CharField(max_length=255, null=True, blank=True)
    credential_hash = models.CharField(max_length=255, null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_auth_methods"
        constraints = [
            models.UniqueConstraint(fields=["user", "provider_type"], name="uq_auth_methods_user_provider"),
        ]
        indexes = [models.Index(fields=["provider_type", "external_id"])]


class Device(BaseModel):
    """Database Blueprint §4.1 `identity.devices`."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="devices", null=True, blank=True)
    device_type = models.CharField(**enum_field_kwargs(DeviceType))
    device_name = models.CharField(max_length=128, null=True, blank=True)
    push_token = models.CharField(max_length=255, null=True, blank=True)
    is_trusted = models.BooleanField(default=False)

    class Meta:
        db_table = "identity_devices"
        verbose_name = _("Device")
        verbose_name_plural = _("Devices")


class UserSession(BaseModel):
    """
    Database Blueprint §4.1 `identity.user_sessions` -- hard-deleted on
    expiry/revoke via a scheduled purge (see infrastructure/tasks.py),
    not soft-deleted, per Database Blueprint §3's session-table
    exception.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    device = models.ForeignKey(Device, on_delete=models.SET_NULL, null=True, blank=True)
    device_name = models.CharField(max_length=128, null=True, blank=True)
    device_type = models.CharField(**enum_field_kwargs(DeviceType))
    refresh_token_hash = models.CharField(max_length=128, unique=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, null=True, blank=True)
    last_activity = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "identity_user_sessions"
        verbose_name = _("User Session")
        verbose_name_plural = _("User Sessions")
        indexes = [
            models.Index(fields=["user", "revoked_at"]),
            models.Index(fields=["expires_at"]),
        ]


class RevokedTokenRecord(AppendOnlyModel):
    """
    Retains a short-lived record of rotated-out refresh token hashes,
    purely to distinguish "token never existed / already purged" from
    "token was validly rotated out" for the reuse-detection check in
    application/services/auth.py::RefreshToken -- append-only by
    design (a rotation event is a fact that happened, never edited).
    """

    session_id = models.UUIDField(db_index=True)
    user_id = models.UUIDField(db_index=True)
    rotated_token_hash = models.CharField(max_length=128, unique=True, db_index=True)

    class Meta:
        db_table = "identity_revoked_token_records"


class Role(BaseModel):
    """Database Blueprint §4.1 `identity.roles`."""

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=128)
    is_system_role = models.BooleanField(default=False)

    class Meta:
        db_table = "identity_roles"
        verbose_name = _("Role")
        verbose_name_plural = _("Roles")

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class Permission(BaseModel):
    """Database Blueprint §4.1 `identity.permissions`."""

    code = models.CharField(max_length=128, unique=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "identity_permissions"
        verbose_name = _("Permission")
        verbose_name_plural = _("Permissions")

    def __str__(self) -> str:  # pragma: no cover
        return self.code


class RolePermission(models.Model):
    """Junction table -- no independent lifecycle, hard-deleted, per Database Blueprint §3's junction-table pattern."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="role_permissions")
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="role_permissions")

    objects = AllObjectsManager()

    class Meta:
        db_table = "identity_role_permissions"
        constraints = [models.UniqueConstraint(fields=["role", "permission"], name="uq_role_permissions_role_permission")]


class UserRole(models.Model):
    """Junction table with optional store scoping -- Database Blueprint §4.1 `identity.user_roles`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="user_roles")
    store_id = models.UUIDField(null=True, blank=True)  # cross-schema ref to stores.stores, no FK

    objects = AllObjectsManager()

    class Meta:
        db_table = "identity_user_roles"
        verbose_name = _("User Role")
        verbose_name_plural = _("User Roles")
        constraints = [
            models.UniqueConstraint(fields=["user", "role", "store_id"], name="uq_user_roles_user_role_store"),
        ]
        indexes = [models.Index(fields=["user"])]


class OTPCodeChallenge(models.Model):
    """
    Database Blueprint §4.1 `identity.otp_codes` -- deliberately does
    NOT use BaseModel/SoftDeleteModel/AppendOnlyModel: it needs mutable
    `attempt_count`/`consumed_at` fields (so it isn't append-only) but
    has no soft-delete/audit value once expired (purged hard by a
    scheduled job, see infrastructure/tasks.py) -- a documented,
    narrow exception to the three-mixin rule, exactly as anticipated by
    Enterprise Database Blueprint §3's own "tables that deviate from
    the standard" section.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    phone_number = models.CharField(max_length=20, db_index=True)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempt_count = models.PositiveIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "identity_otp_codes"
        indexes = [models.Index(fields=["phone_number", "expires_at"])]


class TelegramAuthSessionStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    VERIFIED = "verified", _("Verified")
    EXPIRED = "expired", _("Expired")
    CONSUMED = "consumed", _("Consumed")
    FAILED = "failed", _("Failed")


class TelegramAuthSession(models.Model):
    """
    Phase 3 Telegram automatic login -- the temporary, single-use
    session correlating a "Continue with Telegram" click on the
    website to a real Telegram bot /start deep-link interaction.

    Deliberately follows OTPCodeChallenge's own documented exception
    to the three-mixin rule (mutable status/verified_at/consumed_at
    fields, no audit/soft-delete value once expired). Stores only a
    hashed token (token_hash), never plaintext, matching
    OTPCodeChallenge's own code_hash convention -- the raw token is
    returned to the client exactly once, at creation, and never
    persisted anywhere in recoverable form.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    token_hash = models.CharField(max_length=128, unique=True)
    status = models.CharField(max_length=16, choices=TelegramAuthSessionStatus.choices, default=TelegramAuthSessionStatus.PENDING)
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    user_id = models.UUIDField(null=True, blank=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    objects = AllObjectsManager()

    class Meta:
        db_table = "identity_telegram_auth_sessions"
        indexes = [models.Index(fields=["status", "expires_at"])]


class UserAvatarAsset(BaseModel):
    """
    Processed avatar output from `core.media.MediaPipeline`. Owned by
    `identity` for now (same schema, real FK to `User`) since the
    `content` bounded context's `media_library` table doesn't exist
    yet -- documented interim decision: once `content` is implemented,
    avatar uploads migrate to the standard `profile_picture_media_id ->
    content.media_library` cross-schema-by-ID pattern (Database
    Blueprint §1.2), and this table is retired in favor of that one.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="avatar_assets")
    storage_path = models.CharField(max_length=512)
    webp_path = models.CharField(max_length=512, null=True, blank=True)
    thumbnail_paths = models.JSONField(default=dict, blank=True)
    width_px = models.PositiveIntegerField(null=True, blank=True)
    height_px = models.PositiveIntegerField(null=True, blank=True)
    checksum_sha256 = models.CharField(max_length=64)

    class Meta:
        db_table = "identity_user_avatar_assets"
        indexes = [models.Index(fields=["user", "created_at"])]


class IdentityOutboxEvent(AbstractOutboxEvent):
    """Concrete Outbox table for the `identity` schema (Database Blueprint §6's 'note on the Outbox table itself')."""

    class Meta:
        db_table = "identity_outbox_events"
        ordering = ["created_at"]
