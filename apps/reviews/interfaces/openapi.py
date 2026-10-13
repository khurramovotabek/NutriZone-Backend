"""
Reviews OpenAPI tag registration.

Two tags, matching the established "X / X Admin" 2-tag convention
already used by Loyalty (this module has no separate sub-area the way
Wallet's Ledger/Rewards/Cashback split does -- one aggregate, one
coherent API surface). This file is the single canonical reference
for exactly which tag strings this module owns, so `views.py`'s
`@extend_schema tags=[...]` calls reference these constants rather
than scattering tag strings ad hoc across 14 view classes.
"""
from __future__ import annotations

REVIEWS_TAG = "Reviews"
REVIEWS_ADMIN_TAG = "Reviews Admin"

ALL_REVIEWS_TAGS = (REVIEWS_TAG, REVIEWS_ADMIN_TAG)
