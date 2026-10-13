"""
Identity domain (business) validators.

Structural validation (format/required/length) lives in the value
objects (domain/value_objects.py) and the interface-layer serializers
that call them. This module holds the smaller set of business rules
that don't belong to a single value object's constructor -- rules that
depend on more than one field together.
"""
from __future__ import annotations

from apps.identity.domain.enums import FitnessGoal
from common.exceptions import ValidationFailed


def validate_fitness_goal(value: str | None) -> None:
    if value is None:
        return
    if value not in FitnessGoal.values():
        raise ValidationFailed(
            f"'{value}' is not a recognized fitness goal.",
            details={"fields": [{"field": "goal", "code": "INVALID_CHOICE", "allowed": FitnessGoal.values()}]},
        )


def validate_birthday_is_plausible(age_years: float) -> None:
    """A loose sanity bound -- not a legal-minimum-age business rule (that belongs to a future Terms-of-Service module), just a data-quality guard."""
    if age_years < 0 or age_years > 120:
        raise ValidationFailed(
            "Birthday results in an implausible age.",
            details={"fields": [{"field": "birthday", "code": "IMPLAUSIBLE_VALUE"}]},
        )
