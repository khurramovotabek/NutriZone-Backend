"""
Shared Kernel: Money.

Domain Architecture Specification §5 approves exactly two items as
Shared Kernel: this Money/Currency value object, and the Moderation
domain-service interface *shape* (not implementation). This module is
the code-level home for the former -- the actual implementation lives
in common/utils/money.py to avoid a duplicate class; this module
re-exports it so every app's `domain/value_objects.py` imports Money
from `shared.value_objects.money`, matching the architectural intent
that Shared Kernel code lives under `shared/`, not scattered wherever
convenient.

`shared/` is deliberately the smallest package in the repository, and
its size is a monitored health metric (Django Implementation Blueprint
§1, §16) -- nothing is added here beyond what the Domain Architecture
Specification explicitly approved.
"""
from common.utils.money import DEFAULT_CURRENCY, Money

__all__ = ["DEFAULT_CURRENCY", "Money"]
