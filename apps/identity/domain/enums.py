"""
Identity domain enums.

Each mirrors a Postgres native ENUM type 1:1, per Enterprise Database
Blueprint §2/§4 and Django Implementation Blueprint §6 -- the ORM layer
(`infrastructure/models.py`) builds its `choices=` from these via
`common.utils.enum_field_kwargs`, never redefining the value set.
"""
from __future__ import annotations

from common.utils import DomainStrEnum


class UserStatus(DomainStrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    PENDING_VERIFICATION = "pending_verification"


class FitnessGoal(DomainStrEnum):
    MUSCLE_GAIN = "muscle_gain"
    FAT_LOSS = "fat_loss"
    HEALTHY_LIFESTYLE = "healthy_lifestyle"


class LanguagePreference(DomainStrEnum):
    UZ = "uz"
    RU = "ru"
    EN = "en"


class AuthProviderType(DomainStrEnum):
    """
    PHONE_OTP is the only provider with a working implementation at
    this stage. GOOGLE and TELEGRAM are modeled now (per the mission's
    "prepare architecture... do not implement external API calls yet")
    so `AuthMethod` and the provider-pattern gateway seam
    (infrastructure/gateways/social_auth.py) never need a schema or
    interface change when those integrations are actually built --
    only a concrete gateway implementation is added later.
    """

    PHONE_OTP = "phone_otp"
    GOOGLE = "google"
    TELEGRAM = "telegram"


class DeviceType(DomainStrEnum):
    MOBILE = "mobile"
    WEB = "web"
    POS = "pos"


class SecurityEventType(DomainStrEnum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    OTP_REQUESTED = "otp_requested"
    OTP_VERIFIED = "otp_verified"
    PASSWORD_CHANGED = "password_changed"
    ACCOUNT_BLOCKED = "account_blocked"


class RoleCode(DomainStrEnum):
    """
    The three baseline roles named in the mission. Additional roles
    (future FranchiseOwner, WholesaleBuyer, MarketplaceSeller per
    Enterprise REST API Blueprint §14) are added as new `Role` rows,
    never as new enum members here -- this enum exists only to seed the
    three baseline roles deterministically (see
    infrastructure/fixtures / the `seed_identity_baseline` management
    command), not to close off the role set the way UserStatus closes
    off status values.
    """

    CUSTOMER = "customer"
    STORE_MANAGER = "store_manager"
    SUPER_ADMIN = "super_admin"
