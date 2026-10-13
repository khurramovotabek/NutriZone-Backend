"""
Ordering OpenAPI tag registration.

All 5 tags this phase's brief explicitly names are registered in
`config/settings/base.py`'s `SPECTACULAR_SETTINGS["TAGS"]`, the single
global list every prior module (Cart, Pricing) also registers into --
there is no per-module OpenAPI settings file anywhere else in this
platform. This file exists as the single canonical reference for
exactly which tag strings this module owns, so `views.py`'s
`@extend_schema tags=[...]` calls reference these constants rather
than scattering tag strings ad hoc across 30+ view classes.

Unlike Cart's/Pricing's simpler 2-tag ("X" / "X Admin") convention,
Ordering uses 5 -- this phase's own brief explicitly names Return/
Cancellation/Invoice Operations as distinct tags, and they are applied
that way in `views.py` (return endpoints tagged with
RETURN_OPERATIONS_TAG, etc.), not folded into the generic Ordering/
Ordering Admin tags. This is a deliberate deviation from the 2-tag
precedent, made because it was explicitly instructed, not because the
2-tag convention was found lacking -- flagged here rather than
silently applied either way.
"""
from __future__ import annotations

ORDERING_TAG = "Ordering"
ORDERING_ADMIN_TAG = "Ordering Admin"
RETURN_OPERATIONS_TAG = "Return Operations"
CANCELLATION_OPERATIONS_TAG = "Cancellation Operations"
INVOICE_OPERATIONS_TAG = "Invoice Operations"

ALL_ORDERING_TAGS = (ORDERING_TAG, ORDERING_ADMIN_TAG, RETURN_OPERATIONS_TAG, CANCELLATION_OPERATIONS_TAG, INVOICE_OPERATIONS_TAG)
