"""
Social auth provider gateways -- Google OAuth and Telegram Login.

Per the mission's explicit instruction ("prepare architecture for
Google OAuth / Telegram Login... do not implement external API calls
yet"), both classes below implement the `SocialAuthProvider` Protocol
(application/ports.py) but raise `NotImplementedError` rather than
performing a real network call -- the provider-pattern seam is fully
wired (an `AuthMethod` row with `provider_type=GOOGLE/TELEGRAM` can
already be created and stored, `interfaces/api/v1/` could add
`POST /identity/auth/google` and `POST /identity/auth/telegram`
endpoints that call these gateways today), but the actual OAuth
token-verification / Telegram signature-verification logic is
deliberately out of scope for this phase.
"""
from __future__ import annotations


class GoogleAuthProvider:
    """Verifies a Google ID token and returns its stable `sub` claim as the external_id -- not implemented yet."""

    def verify_and_get_external_id(self, credential: str) -> str:
        raise NotImplementedError(
            "GoogleAuthProvider is a structural placeholder -- Google OAuth token verification "
            "is not implemented in this phase, per the mission's explicit scope boundary."
        )


class TelegramAuthProvider:
    """
    Verifies a Telegram Login Widget payload's HMAC signature (using
    the bot token as the signing key) and returns the Telegram user id
    as the external_id -- not implemented yet.

    When implemented, an invalid signature must raise
    `apps.identity.domain.exceptions.TelegramSignatureInvalidError`,
    already defined and ready in domain/exceptions.py.
    """

    def verify_and_get_external_id(self, credential: str) -> str:
        raise NotImplementedError(
            "TelegramAuthProvider is a structural placeholder -- Telegram Login signature "
            "verification is not implemented in this phase, per the mission's explicit scope boundary."
        )
