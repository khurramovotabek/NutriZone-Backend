"""
Identity-specific health checks (this phase's mission §12): repository
connectivity, OTP provider reachability, token issuer configuration.
Registered against `core.health.registry` from `apps/identity/apps.py`
`ready()` -- `core/health/` never imports this module directly, per the
dependency-direction rule stated in `core/health/registry.py`.
"""
from __future__ import annotations

from django.conf import settings


def check_identity_repository() -> tuple[bool, str]:
    try:
        from apps.identity.infrastructure import models as orm

        orm.User.objects.exists()  # cheapest possible real query against the identity schema
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_otp_provider() -> tuple[bool, str]:
    try:
        from apps.identity.infrastructure.gateways.otp_providers import get_otp_provider

        provider = get_otp_provider()
        provider_name = getattr(settings, "NUTRIZONE_OTP_PROVIDER", "console")
        # A structural reachability check only -- does not send a real
        # OTP. `console` is always "ok"; any other configured provider
        # not yet implemented (Eskiz/PlayMobile/Twilio) is reported
        # explicitly as not-ready rather than silently appearing healthy.
        if provider_name == "console":
            return True, "ok (console provider -- no real SMS delivery)"
        return False, f"provider '{provider_name}' is configured but not yet implemented"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"


def check_token_issuer() -> tuple[bool, str]:
    try:
        jwt_config = getattr(settings, "SIMPLE_JWT", {})
        if not jwt_config.get("SIGNING_KEY"):
            return False, "JWT signing key is not configured"
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"unavailable: {exc}"
