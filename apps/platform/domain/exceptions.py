"""
apps/platform/domain/exceptions.py

Domain Architecture Specification §2.18. Follows every prior module's
established pattern (see e.g. `apps/pricing/domain/exceptions.py`):
module-specific classes inheriting directly from `common.exceptions`'
base hierarchy, never a bare `Exception`.
"""
from __future__ import annotations

from common.exceptions import ConflictError, ValidationFailed


class InvalidRolloutPercentage(ValidationFailed):
    """`rollout_percentage` supplied outside the valid 0-100 range."""


class DuplicateFlagKey(ConflictError):
    """A flag with this `key` already exists -- `key` is unique (Database Blueprint §4.18 `uq_feature_flags_key`)."""
