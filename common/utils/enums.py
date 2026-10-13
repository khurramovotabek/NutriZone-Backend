"""
Base enum helpers.

Every `apps/<context>/domain/enums.py` enum mirrors the Postgres native
`ENUM` type of the same name 1:1 (Enterprise Database Blueprint §2/§4,
Django Implementation Blueprint §6). `DomainStrEnum` is the base class
those enums use; `as_django_choices()` bridges a domain enum to Django's
`TextChoices`-shaped `(value, label)` tuples for use in
`infrastructure/models.py` field `choices=` -- so the domain layer stays
the single source of truth for the value set, not the ORM layer.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class DomainStrEnum(StrEnum):
    """Base class for domain-layer enums. Zero Django dependency."""

    @classmethod
    def as_django_choices(cls) -> list[tuple[str, str]]:
        return [(member.value, member.name.replace("_", " ").title()) for member in cls]

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]


class GenericStatus(DomainStrEnum):
    """
    A generic status enum for apps that need a placeholder before their
    real domain-specific status enum is defined (MIC §1 step 4) -- not
    intended for direct use in a real model; each module defines its own
    status enum (e.g. OrderStatus, ReturnStatus) per its Domain
    Architecture Specification entry.
    """

    ACTIVE = "active"
    INACTIVE = "inactive"


def enum_field_kwargs(enum_cls: type[DomainStrEnum], **overrides: Any) -> dict[str, Any]:
    """Convenience for building a Django CharField's choices/max_length kwargs from a DomainStrEnum."""
    choices = enum_cls.as_django_choices()
    max_length = max(len(value) for value, _ in choices) if choices else 32
    kwargs: dict[str, Any] = {"choices": choices, "max_length": max_length}
    kwargs.update(overrides)
    return kwargs
