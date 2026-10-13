"""
Cryptographic infrastructure: OTP code hashing and JWT token issuance.

Deliberately kept out of `domain/` (which needs a hasher/issuer handed
to it as a callable/Protocol, per MIC §4's "domain service touches no
I/O" rule) and out of `application/` (which depends only on the
`TokenIssuer` Protocol in ports.py) -- this is exactly the kind of
crypto/third-party-library detail `infrastructure/` exists to own.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from rest_framework_simplejwt.tokens import AccessToken as SimpleJWTAccessToken
from rest_framework_simplejwt.tokens import RefreshToken as SimpleJWTRefreshToken

from apps.identity.domain.services import TokenPolicy
from core.clock import Clock


def hash_otp_code(code: str) -> str:
    """
    SHA-256 with a server-side pepper (never store plaintext OTP codes,
    per Architecture Review §14). The pepper is `SECRET_KEY`-derived
    rather than a separate secret to avoid introducing a second
    secrets-management requirement for a foundation-phase module --
    revisit if a dedicated OTP pepper becomes a compliance requirement.
    """
    pepper = settings.SECRET_KEY
    return hashlib.sha256(f"{pepper}:{code}".encode()).hexdigest()


def hash_refresh_token(raw_token: str) -> str:
    """Refresh tokens are opaque JWTs -- hashed before storage so a DB read alone never yields a usable token (Architecture Review §14)."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class _IssuedTokenPair:
    access_token: str
    refresh_token: str
    refresh_token_hash: str
    refresh_expires_at: datetime


_WS_TICKET_LIFETIME = timedelta(seconds=60)


def issue_ws_ticket(user_id: uuid.UUID) -> str:
    """
    A real, validly-signed access token (same secret/algorithm
    `core.channels_auth.jwt_auth_middleware.JWTAuthMiddleware` already
    validates every WebSocket connection against) but with a lifetime
    of seconds, not minutes -- minted fresh per connection attempt,
    never the real long-lived access token. Exists solely because a
    browser cannot attach a custom `Authorization` header to a
    WebSocket handshake, and the real access token is deliberately
    HttpOnly (never reaches client JS, per session.ts's own
    documented rationale) -- this is the one, narrow, short-lived
    exception that lets a socket open at all, not a weakening of that
    rule.
    """
    token = SimpleJWTAccessToken()
    token["user_id"] = str(user_id)
    token.set_exp(lifetime=_WS_TICKET_LIFETIME)
    return str(token)


class SimpleJWTTokenIssuer:
    """Concrete `TokenIssuer` (ports.py) backed by djangorestframework-simplejwt."""

    def issue(self, user_id: uuid.UUID) -> _IssuedTokenPair:
        refresh = SimpleJWTRefreshToken()
        refresh["user_id"] = str(user_id)
        access = refresh.access_token
        access["user_id"] = str(user_id)

        raw_refresh = str(refresh)
        return _IssuedTokenPair(
            access_token=str(access),
            refresh_token=raw_refresh,
            refresh_token_hash=hash_refresh_token(raw_refresh),
            refresh_expires_at=TokenPolicy.refresh_token_expiry(),
        )

    def blacklist_refresh_token(self, raw_refresh_token: str) -> None:
        try:
            token = SimpleJWTRefreshToken(raw_refresh_token)
            token.blacklist()
        except Exception:  # noqa: BLE001 - an already-invalid/expired token is a no-op, not an error
            pass

    def hash_refresh_token(self, raw_refresh_token: str) -> str:
        return hash_refresh_token(raw_refresh_token)
