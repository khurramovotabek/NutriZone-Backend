"""
Feature flag key catalogue.

A closed, typed enum -- `FeatureFlags.is_enabled()` (see engine.py)
only accepts a `FlagKey` member, never an arbitrary string, so a typo'd
flag name fails at call-site type-check time rather than silently
always evaluating to "disabled" at runtime.

These are infrastructure-level master switches for entire bounded
contexts / major capabilities -- distinct from the *business* feature
flags the `platform` app's `feature_flags` database table will manage
once that module is implemented (Database Blueprint §4.18, Django
Implementation Blueprint §7's "business flags need to change without a
redeploy" case). Both categories share this same evaluation engine and
`FlagProvider` interface (see providers.py) -- when `platform` is
implemented, its DB-backed provider plugs into the same engine rather
than reinventing flag evaluation.
"""
from __future__ import annotations

from enum import StrEnum


class FlagKey(StrEnum):
    ENABLE_AI = "ENABLE_AI"
    ENABLE_CHAT = "ENABLE_CHAT"
    ENABLE_POS = "ENABLE_POS"
    ENABLE_ANALYTICS = "ENABLE_ANALYTICS"
    ENABLE_WALLET = "ENABLE_WALLET"
    ENABLE_MARKETPLACE = "ENABLE_MARKETPLACE"
    ENABLE_B2B = "ENABLE_B2B"
    ENABLE_WHOLESALE = "ENABLE_WHOLESALE"
