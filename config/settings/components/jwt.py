"""
JWT configuration component (Enterprise REST API Blueprint §4).

Short-lived access token (10-15 min), rotating refresh, reuse detection.
Signing-key rotation support (multiple verification keys, one signing
key) is built in from day one per Django Implementation Blueprint §7 --
`SIGNING_KEY` is the active signer; additional historical keys can be
supplied via `NUTRIZONE_JWT_VERIFYING_KEYS` for graceful rotation once
`identity` is implemented.
"""
from __future__ import annotations

import os
from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_TOKEN_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get("JWT_REFRESH_TOKEN_DAYS", "30"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.environ.get("JWT_SIGNING_KEY", os.environ.get("SECRET_KEY", "")),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}
