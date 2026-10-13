"""
Encryption at rest for payment-provider secrets (Payme key, Click secret, Uzum password ...).

Fernet (AES-128-CBC + HMAC-SHA256). The key comes from settings.PAYMENT_SECRETS_KEY (a urlsafe
base64 Fernet key -- recommended in production, so rotating SECRET_KEY doesn't lose the secrets),
else it is derived from SECRET_KEY. Values are only ever decrypted server-side, at the moment a
provider request must be signed or verified; the dashboard shows a masked hint, never the value.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger("nutrizone.app")


def _fernet() -> Fernet:
    key = getattr(settings, "PAYMENT_SECRETS_KEY", "") or ""
    if not key:
        key = base64.urlsafe_b64encode(hashlib.sha256(f"nz-payment-secrets:{settings.SECRET_KEY}".encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secrets(values: dict[str, str]) -> str:
    clean = {k: v for k, v in values.items() if v}
    return _fernet().encrypt(json.dumps(clean, sort_keys=True).encode()).decode() if clean else ""


def decrypt_secrets(token: str) -> dict[str, str]:
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(token.encode()).decode())
    except (InvalidToken, ValueError):
        # Key changed (SECRET_KEY rotated without PAYMENT_SECRETS_KEY): treat as not configured, never crash checkout.
        logger.error("payment: provider secrets could not be decrypted -- re-enter them on the dashboard")
        return {}


def mask(value: str) -> str:
    """'abcd…wxyz' style hint for the dashboard (never more than the last 4 characters)."""
    if not value:
        return ""
    return f"••••••{value[-4:]}" if len(value) > 6 else "••••••"
