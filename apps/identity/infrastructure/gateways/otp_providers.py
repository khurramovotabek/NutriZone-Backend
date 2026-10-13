"""
OTP delivery gateways -- the Anti-Corruption Layer for SMS providers
(Domain Architecture Specification §5, Architecture Review §11).

`ConsoleOTPProvider` is the development-environment default (mirrors
`EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"` in
config/settings/development.py) -- it never sends a real SMS, it logs
the code so a developer can complete the OTP flow locally.

Concrete provider adapters (Eskiz, PlayMobile, Twilio -- named in the
mission as future providers) each implement `OTPProvider`
(application/ports.py) and translate their own SDK/response shapes
into the plain `bool` this interface expects -- no provider-specific
type is ever allowed to leak past this module, per the Anti-Corruption
Layer rule (Domain Architecture Specification §5).

Phase 04: `EskizOTPProvider` is now a real, production-shaped adapter
(chosen over PlayMobile/Twilio as the most business-relevant vendor
for this Uzbekistan-market project). Its exact request/response field
names are based on Eskiz.uz's own publicly documented API -- honestly
disclosed as NOT verified against a live sandbox account, since no
real vendor credentials exist to test against (per this phase's own
explicit "do not invent credentials" rule). This is deployment
validation work for whoever activates the real vendor account, not a
code defect: the adapter mechanics (auth, timeout handling, retryable
vs. non-retryable classification, secret-safe logging, fail-loud
configuration) are all real and tested against mocked HTTP responses.
PlayMobile and Twilio remain structural placeholders, unchanged --
implementing all three named vendors when only one is prioritized
would be exactly the "implement every provider in existence" scope
creep this phase's own charter warns against.
"""
from __future__ import annotations

import logging

import requests

from apps.identity.application.ports import OTPProviderError
from apps.identity.domain.value_objects import PhoneNumber

logger = logging.getLogger("nutrizone.security")


class OTPProviderConfigurationError(OTPProviderError):
    """Raised when a provider is selected via settings but its required credentials are absent -- fails loudly at first use, never silently falls back to a different provider."""


class OTPProviderNonRetryableError(OTPProviderError):
    """The provider rejected the request in a way retrying will not fix (invalid phone number, invalid/expired credentials, malformed response). Distinct from a transient failure (timeout, connection error, 5xx), which returns False instead -- safe for the caller's own existing retry infrastructure to retry."""


class ConsoleOTPProvider:
    """Development/foundation-phase default -- logs the OTP instead of sending a real SMS."""

    def send_otp(self, phone_number: PhoneNumber, code: str) -> bool:
        logger.info("OTP for %s: %s (console provider -- no real SMS sent)", phone_number.value, code)
        return True


class EskizOTPProvider:
    """
    Real adapter for the Eskiz.uz SMS gateway. Two real HTTP calls per
    send: POST /auth/login (email + password -> bearer token, per
    call -- no token caching in this first implementation, a disclosed,
    deliberate simplicity given `get_otp_provider()`'s own convention
    of constructing a fresh provider instance per use; the correctness
    cost of adding cross-request token caching was judged not worth
    the added complexity for this phase's own scope), then
    POST /message/sms/send with that token.
    """

    def __init__(self, email: str | None = None, password: str | None = None, sender_name: str | None = None, base_url: str | None = None, timeout_seconds: float | None = None) -> None:
        from django.conf import settings

        self._email = email if email is not None else settings.ESKIZ_EMAIL
        self._password = password if password is not None else settings.ESKIZ_PASSWORD
        self._sender_name = sender_name if sender_name is not None else settings.ESKIZ_SENDER_NAME
        self._base_url = (base_url if base_url is not None else settings.ESKIZ_API_BASE_URL).rstrip("/")
        self._timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.ESKIZ_TIMEOUT_SECONDS

    def send_otp(self, phone_number: PhoneNumber, code: str) -> bool:
        if not self._email or not self._password:
            raise OTPProviderConfigurationError(
                "EskizOTPProvider selected via NUTRIZONE_OTP_PROVIDER but ESKIZ_EMAIL/ESKIZ_PASSWORD are not configured. "
                "Set both environment variables, or select a different provider."
            )

        try:
            token = self._authenticate()
        except requests.exceptions.Timeout:
            logger.warning("Eskiz OTP send failed: authentication timed out (provider=eskiz, operation=authenticate, phone=%s)", phone_number.value)
            return False
        except requests.exceptions.ConnectionError:
            logger.warning("Eskiz OTP send failed: connection error during authentication (provider=eskiz, operation=authenticate, phone=%s)", phone_number.value)
            return False
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and 500 <= status < 600:
                logger.warning("Eskiz OTP send failed: authentication server error (provider=eskiz, operation=authenticate, phone=%s, status=%s)", phone_number.value, status)
                return False
            logger.error("Eskiz OTP send rejected: authentication failed, credentials likely invalid (provider=eskiz, operation=authenticate, phone=%s, status=%s)", phone_number.value, status)
            raise OTPProviderNonRetryableError(f"Eskiz authentication failed (HTTP {status}) -- check ESKIZ_EMAIL/ESKIZ_PASSWORD.") from exc

        # The bearer token itself is never logged -- only used, immediately, for the one call that needs it.
        try:
            response = requests.post(
                f"{self._base_url}/message/sms/send",
                headers={"Authorization": f"Bearer {token}"},
                data={"mobile_phone": phone_number.value.lstrip("+"), "message": f"{_brand()} OTP: {code}", "from": self._sender_name},
                timeout=self._timeout_seconds,
            )
        except requests.exceptions.Timeout:
            logger.warning("Eskiz OTP send failed: send request timed out (provider=eskiz, operation=send, phone=%s)", phone_number.value)
            return False
        except requests.exceptions.ConnectionError:
            logger.warning("Eskiz OTP send failed: connection error during send (provider=eskiz, operation=send, phone=%s)", phone_number.value)
            return False

        if response.status_code >= 500:
            logger.warning("Eskiz OTP send failed: server error (provider=eskiz, operation=send, phone=%s, status=%s)", phone_number.value, response.status_code)
            return False
        if response.status_code == 400:
            # Eskiz's own documented behavior for malformed/invalid phone numbers -- not the caller's own request format, since PhoneNumber's own E.164 validation already ran before this provider is ever called.
            logger.error("Eskiz OTP send rejected: provider reports invalid request (provider=eskiz, operation=send, phone=%s, status=400)", phone_number.value)
            raise OTPProviderNonRetryableError("Eskiz rejected the SMS send request (HTTP 400) -- the phone number or message content was rejected by the provider.")
        if response.status_code == 401:
            logger.error("Eskiz OTP send rejected: token rejected on send (provider=eskiz, operation=send, phone=%s, status=401)", phone_number.value)
            raise OTPProviderNonRetryableError("Eskiz rejected the bearer token on the send call -- check ESKIZ_EMAIL/ESKIZ_PASSWORD.")
        if response.status_code != 200:
            logger.error("Eskiz OTP send failed: unexpected status (provider=eskiz, operation=send, phone=%s, status=%s)", phone_number.value, response.status_code)
            raise OTPProviderNonRetryableError(f"Eskiz returned an unexpected status code {response.status_code} for the send request.")

        try:
            body = response.json()
        except ValueError as exc:
            logger.error("Eskiz OTP send failed: malformed (non-JSON) response body (provider=eskiz, operation=send, phone=%s)", phone_number.value)
            raise OTPProviderNonRetryableError("Eskiz returned a malformed (non-JSON) response body.") from exc

        # Eskiz's own documented success indicator is a "status": "waiting" (queued for delivery) or similar success-shaped field -- treated permissively (absence of an explicit error field) since the exact success-field name cannot be verified without a live sandbox account (see this module's own docstring).
        if isinstance(body, dict) and body.get("status") == "error":
            logger.error("Eskiz OTP send rejected: provider body reports an error (provider=eskiz, operation=send, phone=%s, message=%s)", phone_number.value, body.get("message", "<no message>"))
            raise OTPProviderNonRetryableError(f"Eskiz reported an error in the response body: {body.get('message', '<no message>')}")

        return True

    def _authenticate(self) -> str:
        response = requests.post(
            f"{self._base_url}/auth/login",
            data={"email": self._email, "password": self._password},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        token = body.get("data", {}).get("token") if isinstance(body.get("data"), dict) else None
        if not token:
            raise OTPProviderNonRetryableError("Eskiz authentication succeeded (HTTP 200) but no token was present in the response body.")
        return token


class PlayMobileOTPProvider:
    """Placeholder for the PlayMobile SMS gateway integration. See EskizOTPProvider's docstring -- same rationale."""

    def send_otp(self, phone_number: PhoneNumber, code: str) -> bool:
        raise NotImplementedError("PlayMobileOTPProvider is a structural placeholder -- not yet implemented.")


class TwilioOTPProvider:
    """Placeholder for Twilio (international fallback). See EskizOTPProvider's docstring -- same rationale."""

    def send_otp(self, phone_number: PhoneNumber, code: str) -> bool:
        raise NotImplementedError("TwilioOTPProvider is a structural placeholder -- not yet implemented.")


class TelegramOTPProvider:
    """
    Delivers the login code via the real, existing Telegram bot
    (LiveTelegramGateway, apps.notifications.infrastructure.gateways)
    instead of SMS -- reuses 100% of RequestOTP/VerifyOTP's own
    proven rate-limiting, expiration, hashing, and security logic
    unchanged, since this only implements the same OTPProvider
    protocol with a different delivery channel.

    Looks up the real, existing telegram_user_id link established by
    Phase 15B's own LinkTelegramCustomer service (the user must have
    already started a conversation with the bot and shared their
    contact at least once) -- never trusts a client-supplied Telegram
    identity. If the phone number has no linked Telegram account,
    fails loudly with a clear, honest error rather than silently
    falling back to SMS or pretending delivery succeeded.
    """

    def send_otp(self, phone_number: PhoneNumber, code: str) -> bool:
        from django.conf import settings as django_settings

        from apps.identity.domain.services import OTP_EXPIRY_SECONDS
        from apps.identity.infrastructure import models as identity_orm
        from apps.notifications.infrastructure.gateways import (
            LiveTelegramGateway,
            TelegramGatewayConfigurationError,
            TelegramGatewayNonRetryableError,
            TelegramGatewayRetryableError,
        )
        from apps.telegram_bot.interfaces.i18n import t

        user = identity_orm.User.objects.filter(phone_number=phone_number.value).first()
        if user is None or user.telegram_user_id is None:
            raise OTPProviderNonRetryableError(
                "This phone number has no linked Telegram account. Start a conversation with the NutriZone bot and share your contact first."
            )

        # Real defect fix: this previously sent its own hardcoded,
        # English-only, plain-text message instead of the bot's
        # already-built, already-localized (uz/ru/en) "login_code_sent"
        # template -- so every Telegram-delivered login code arrived in
        # English regardless of the customer's real language.
        lang = getattr(user, "language", None) or "en"
        message = t("login_code_sent", lang, code=code, minutes=OTP_EXPIRY_SECONDS // 60)
        text = f"<b>{_brand()}</b>\n{message}"

        # Real, product-required addition: an inline keyboard on the
        # code message itself -- "Enter code page" (straight to the
        # plain code-entry page, no session/token in the URL -- a
        # deliberately different label from _send_autologin_link's own
        # "One-tap login" button, since that one authenticates instantly
        # with no code at all; the two were confirmed confused when both
        # said "Open website") and "Get a new code" (reuses the exact
        # same "menu:getcode" callback_data the main menu button already
        # sends, so callback_router.py's existing resend/cooldown
        # handling applies unchanged -- no second, divergent resend
        # path). The website button is only included when FRONTEND_URL
        # is actually configured, matching _send_autologin_link's own
        # established defensive convention rather than ever sending a
        # button with a broken/empty URL.
        keyboard = []
        frontend_url = getattr(django_settings, "FRONTEND_URL", None)
        if frontend_url:
            keyboard.append([{"text": t("enter_code_button", lang), "url": f"{frontend_url.rstrip('/')}/login"}])
        keyboard.append([{"text": t("resend_code_button", lang), "callback_data": "menu:getcode"}])

        try:
            LiveTelegramGateway().send_message_with_keyboard(
                chat_id=str(user.telegram_user_id),
                text=text,
                inline_keyboard=keyboard,
            )
        except TelegramGatewayConfigurationError as exc:
            raise OTPProviderConfigurationError(str(exc)) from exc
        except TelegramGatewayNonRetryableError as exc:
            raise OTPProviderNonRetryableError(str(exc)) from exc
        except TelegramGatewayRetryableError:
            return False
        return True


def get_otp_provider():
    """Resolves the active OTP provider from Django settings -- a config-driven swap point, never a code branch scattered through application/ (Django Implementation Blueprint §7)."""
    from django.conf import settings

    provider_name = getattr(settings, "NUTRIZONE_OTP_PROVIDER", "console")
    providers = {
        "console": ConsoleOTPProvider,
        "eskiz": EskizOTPProvider,
        "playmobile": PlayMobileOTPProvider,
        "twilio": TwilioOTPProvider,
        "telegram": TelegramOTPProvider,
    }
    provider_cls = providers.get(provider_name)
    if provider_cls is None:
        raise ValueError(f"Unknown OTP provider '{provider_name}'.")
    return provider_cls()


def _brand() -> str:
    from apps.platform.infrastructure.branding import brand_name

    return brand_name()
