"""
Reusable structural validators.

Referenced by both `infrastructure/models.py` field validators and
`interfaces/api/v1/serializers.py` (Django Implementation Blueprint §5)
so the same validation function is never implemented twice and drifting
out of sync. These are STRUCTURAL (input-tier) validators only -- see
MIC §6 for the four-tier validation split; business validation belongs
in each app's `domain/validators.py`, not here.
"""
from __future__ import annotations

import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

E164_PHONE_RE = re.compile(r"^\+[1-9]\d{1,14}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_phone_number(value: str) -> None:
    """E.164 format, per Database Blueprint §4.1 `users.phone_number`."""
    if not E164_PHONE_RE.match(value):
        raise ValidationError(_("Phone number must be in E.164 format, e.g. +998901234567."), code="invalid_format")


def validate_otp_code(value: str) -> None:
    if not (value.isdigit() and len(value) == 6):
        raise ValidationError(_("OTP code must be exactly 6 digits."), code="invalid_format")


def validate_money_amount(value: Decimal) -> None:
    """Non-negative, per the `ck_*_amount_nonnegative`-style constraints throughout the Database Blueprint."""
    if value < Decimal("0"):
        raise ValidationError(_("Amount must not be negative."), code="negative_amount")


def validate_positive_quantity(value: int) -> None:
    if value <= 0:
        raise ValidationError(_("Quantity must be a positive integer."), code="non_positive_quantity")


def validate_slug_format(value: str) -> None:
    if not SLUG_RE.match(value):
        raise ValidationError(_("Slug must be lowercase, alphanumeric, hyphen-separated."), code="invalid_slug")
