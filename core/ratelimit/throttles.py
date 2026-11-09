"""
DRF throttle bridge.

Wraps `core.ratelimit.limiter.RateLimiter` in DRF's `BaseThrottle`
interface so an endpoint-specific limit (REST API Blueprint §13's
per-module overrides: OTP 3/hr, coupon validate 10/min, etc.) can be
declared as a normal DRF `throttle_classes` entry rather than
duplicating rate-limit bookkeeping per view.
"""
from __future__ import annotations

import hmac
from typing import TYPE_CHECKING

from django.conf import settings
from rest_framework import throttling
from rest_framework.request import Request
from rest_framework.throttling import BaseThrottle

from core.ratelimit.limiter import RateLimiter

if TYPE_CHECKING:
    # annotation only: importing rest_framework.views here is circular -- APIView's class body reads
    # DEFAULT_THROTTLE_CLASSES, which names the classes below
    from rest_framework.views import APIView


class ScopedRateLimitThrottle(BaseThrottle):
    """
    Base class -- a concrete throttle subclasses this and sets `scope`,
    `limit`, `window_seconds` (matching REST API Blueprint §18's
    per-endpoint table), e.g.:

        class OTPRequestThrottle(ScopedRateLimitThrottle):
            scope = "otp_request"
            limit = 3
            window_seconds = 3600
            identifier_field = "phone_number"  # read from request.data

    `identifier_source` controls whether the limiter keys on the
    authenticated user, the client IP, or a request-body field --
    matching the mission's "Per-IP / Per-user / Per-endpoint" dimensions.
    """

    scope: str = ""
    limit: int = 0
    window_seconds: int = 60
    identifier_source: str = "ip"  # "ip" | "user" | "field:<name>"

    def __init__(self) -> None:
        if not self.scope or self.limit <= 0:
            raise ValueError(f"{self.__class__.__name__} must define a non-empty scope and a positive limit.")
        self._limiter = RateLimiter(scope=self.scope, limit=self.limit, window_seconds=self.window_seconds)
        self._last_result = None

    def _resolve_identifier(self, request: Request) -> str:
        if self.identifier_source == "user":
            user = getattr(request, "user", None)
            if user is not None and getattr(user, "is_authenticated", False):
                return f"user:{user.id}"
            return f"ip:{self.get_ident(request)}"
        if self.identifier_source.startswith("field:"):
            field_name = self.identifier_source.split(":", 1)[1]
            value = request.data.get(field_name) if hasattr(request, "data") else None
            return f"{field_name}:{value or self.get_ident(request)}"
        return f"ip:{self.get_ident(request)}"

    def allow_request(self, request: Request, view: APIView) -> bool:
        identifier = self._resolve_identifier(request)
        self._last_result = self._limiter.check(identifier)
        return self._last_result.allowed

    def wait(self) -> float | None:
        if self._last_result is None:
            return None
        return float(self._last_result.retry_after_seconds) or None


def is_trusted_server(request) -> bool:
    """
    True for a call from our own storefront server (Next.js SSR, route handlers, sitemap), which sends the shared
    `X-Internal-Token` (settings.INTERNAL_API_TOKEN). Every one of those calls reaches Django from the same address,
    so the coarse per-IP tier below made the whole storefront share one 100/min budget: 4 867 responses of 429 in
    the week to 2026-11-09 (catalogue pages, settings, the sitemap cut off at 1 000 of 1 185 products).
    An empty or short token disables the bypass.
    """
    token = getattr(settings, "INTERNAL_API_TOKEN", "") or ""
    if len(token) < 32:
        return False
    sent = request.META.get("HTTP_X_INTERNAL_TOKEN", "")
    return bool(sent) and hmac.compare_digest(sent.encode(), token.encode())


class AnonRateThrottle(throttling.AnonRateThrottle):
    """DRF's global anonymous tier, skipped for our own storefront server (`is_trusted_server`)."""

    def allow_request(self, request, view) -> bool:
        return is_trusted_server(request) or super().allow_request(request, view)


class UserRateThrottle(throttling.UserRateThrottle):
    """DRF's global per-user tier, skipped for our own storefront server. Endpoint limits (login, OTP...) still apply."""

    def allow_request(self, request, view) -> bool:
        return is_trusted_server(request) or super().allow_request(request, view)
