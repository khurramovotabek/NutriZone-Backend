"""
POS OpenAPI tag registration.

One tag only -- `POS`. No `POS Admin`/`POS Cashier`/`POS Payments`
split, matching this phase's own explicit Section 13 preference and
mirroring Analytics' own single-tag precedent (re-verified this
phase, not assumed): every capability in this module is a generic
Sale-lifecycle operation, not a distinction between self-service and
staff-admin roles the way Reviews'/Chat's/Notifications' own 2-tag
split represents -- POS has no per-user ownership concept at all
(re-confirmed in Step 1; `Sale` has no user-scoping field).
"""
from __future__ import annotations

POS_TAG = "POS"

ALL_POS_TAGS = (POS_TAG,)
