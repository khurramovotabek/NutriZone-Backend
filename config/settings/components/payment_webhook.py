"""
Payment webhook signature-verification secret (Phase 02E). Matches
`jwt.py`'s own established pattern -- a dedicated env var with a
fallback, since this repository has no dedicated payment provider yet
(confirmed: `apps/ordering/infrastructure/gateways/payment_gateway.py`
is a deliberate placeholder) and this secret protects the internal,
provider-agnostic webhook contract described in that gateway's own
docstring, not any specific third-party provider's own signing scheme.
"""
from __future__ import annotations

import os

PAYMENT_WEBHOOK_SECRET = os.environ.get("PAYMENT_WEBHOOK_SECRET", os.environ.get("SECRET_KEY", ""))
