"""
Identity domain value objects.

Immutable, self-validating. `PhoneNumber` and `OTPCode` in particular
encode the exact format rules the Architecture Review §14 and Database
Blueprint §4.1 specify -- validation lives here (domain), not
duplicated in the serializer layer (interfaces), per MIC §6's
"business rule implemented in exactly one place" rule. The serializer
layer calls these same value-object constructors for its structural
validation instead of re-implementing the regex.
"""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

from apps.identity.domain.enums import FitnessGoal
from common.exceptions import ValidationFailed

_E164_RE = re.compile(r"^\+[1-9]\d{1,14}$")


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    value: str

    def __post_init__(self) -> None:
        if not _E164_RE.match(self.value):
            raise ValidationFailed(
                "Phone number must be in E.164 format, e.g. +998901234567.",
                details={"fields": [{"field": "phone_number", "code": "INVALID_FORMAT"}]},
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Email:
    value: str

    _EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    def __post_init__(self) -> None:
        if not self._EMAIL_RE.match(self.value):
            raise ValidationFailed(
                "Invalid email format.",
                details={"fields": [{"field": "email", "code": "INVALID_FORMAT"}]},
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class OTPCode:
    """A 6-digit numeric OTP code. Generation and hashing are separate concerns (see OTPPolicy/OTPHasher)."""

    value: str

    def __post_init__(self) -> None:
        if not (self.value.isdigit() and len(self.value) == 6):
            raise ValidationFailed(
                "OTP code must be exactly 6 digits.",
                details={"fields": [{"field": "otp_code", "code": "INVALID_FORMAT"}]},
            )

    @staticmethod
    def generate() -> "OTPCode":
        """Cryptographically secure 6-digit code -- never `random.randint`."""
        return OTPCode(f"{secrets.randbelow(1_000_000):06d}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class PermissionCode:
    """
    A `<context>.<resource>.<action>` permission string, matching the
    exact vocabulary the Domain Architecture Specification and
    Enterprise REST API Blueprint §14's Permission Matrix use
    throughout (e.g. "products.view", "orders.manage").
    """

    value: str

    _RE = re.compile(r"^[a-z_]+\.[a-z_]+\.[a-z_]+$")

    def __post_init__(self) -> None:
        if not self._RE.match(self.value):
            raise ValidationFailed(
                "Permission code must match '<context>.<resource>.<action>'.",
                details={"fields": [{"field": "permission_code", "code": "INVALID_FORMAT"}]},
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class FitnessProfile:
    """Optional physical/goal profile -- a value object rather than three loose nullable fields, since the three fields are conceptually one cohesive thing a customer edits together."""

    height_cm: float | None = None
    weight_kg: float | None = None
    goal: FitnessGoal | None = None
    """A real defect fix: previously typed as a plain, unvalidated `str` -- the comment justifying this claimed a domain/enums <-> value_objects import cycle that does not actually exist (`enums.py` has zero dependency on this module, confirmed directly). Any arbitrary string could previously be stored as a "goal"; construction now raises ValidationFailed for anything that isn't a real FitnessGoal member."""

    def __post_init__(self) -> None:
        if self.height_cm is not None and not (30 <= self.height_cm <= 300):
            raise ValidationFailed(
                "Height must be between 30 and 300 cm.",
                details={"fields": [{"field": "height_cm", "code": "OUT_OF_RANGE"}]},
            )
        if self.weight_kg is not None and not (10 <= self.weight_kg <= 500):
            raise ValidationFailed(
                "Weight must be between 10 and 500 kg.",
                details={"fields": [{"field": "weight_kg", "code": "OUT_OF_RANGE"}]},
            )
        if self.goal is not None and not isinstance(self.goal, FitnessGoal):
            try:
                object.__setattr__(self, "goal", FitnessGoal(self.goal))
            except ValueError as exc:
                raise ValidationFailed(
                    f"'{self.goal}' is not a valid fitness goal.",
                    details={"fields": [{"field": "goal", "code": "INVALID_CHOICE"}]},
                ) from exc
