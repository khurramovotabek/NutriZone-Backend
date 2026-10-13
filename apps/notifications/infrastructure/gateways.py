"""
Notifications Anti-Corruption Layer gateways.

**Only 1 gateway exists, deliberately -- `TelegramGateway`.** This
phase's own instructions are explicit: real evidence exists that
Telegram is an established contact channel (`apps.identity.domain.
aggregates.User.telegram_username`, confirmed in this phase's own
Step 1), but that evidence does NOT automatically justify implementing
a real Telegram Bot API client. A repository-wide search during Step
1 found zero existing Telegram bot infrastructure, zero HTTP client
convention for external providers, zero bot-token configuration, and
zero secrets/credentials pattern anywhere in this codebase.

**No `EmailGateway`, `SmsGateway`, or `PushGateway` exists.** Per this
phase's own explicit instruction ("do not infer channels merely
because they are common in notification systems... only implement
channels supported by actual project evidence"), no equivalent
evidence for these channels was found anywhere in the repository
during Step 1 (no email-sending infrastructure, no SMS provider
configuration, no push-notification/FCM configuration). Certified
Domain does model `NotificationChannel.EMAIL`/`SMS`/`PUSH` as valid
enum values (a business classification), but the enum's existence is
not, by itself, evidence that a real provider integration exists or
should be fabricated here.

Phase 04: `TelegramGateway` is now backed by a real adapter
(`LiveTelegramGateway`) implementing the Bot API's own well-known,
stable, publicly documented `sendMessage` endpoint -- chosen over
inventing Email/SMS/Push infrastructure this repository has zero
evidence for. Config-driven via `NUTRIZONE_TELEGRAM_GATEWAY`
(`disabled` remains the default -- `NotImplementedTelegramGateway`,
unchanged, still fails loudly rather than silently no-op'ing), matching
the same swap-point convention already established by
`NUTRIZONE_OTP_PROVIDER`.
"""
from __future__ import annotations

import logging
from typing import Protocol

import requests

logger = logging.getLogger("nutrizone.notifications")


class TelegramGateway(Protocol):
    def send_message(self, telegram_username: str, title: str, body: str) -> str:
        """Returns a provider message reference on success (see `NotificationDelivery.provider_reference`)."""
        ...

    def send_contact_request(self, chat_id: str, text: str, button_text: str) -> str:
        """Sends `text` with a reply keyboard containing a single `request_contact` button -- lets the user share their real phone number via Telegram's own native contact-sharing UI in one tap, rather than needing to know the attachment-menu path unassisted."""
        ...

    def send_location_request(self, chat_id: str, text: str, button_text: str) -> str:
        """Sends `text` with a reply keyboard containing a single `request_location` button -- lets the user share their real delivery location via Telegram's own native location-sharing UI in one tap, matching send_contact_request's identical role for phone numbers."""
        ...

    def send_photo(self, chat_id: str, photo_url: str, caption: str, inline_keyboard: list[list[dict]] | None = None) -> str:
        """Sends a photo (by public URL) with an optional caption and inline keyboard -- used by the Orders Channel notification to show the ordered product's real image alongside order details."""
        ...

    def edit_message_media(self, chat_id: str, message_id: str, photo_url: str, caption: str, inline_keyboard: list[list[dict]] | None = None) -> None:
        """Replaces an already-sent photo message's image/caption/keyboard in place (Bot API `editMessageMedia`) -- used by the product browsing card so paging through a catalog edits one message instead of sending a new photo per product."""
        ...

    def send_venue(self, chat_id: str, latitude: float, longitude: float, title: str, address: str, reply_to: str | None = None, inline_keyboard: list[list[dict]] | None = None) -> str:
        """A real map pin (Bot API `sendVenue`): opens in the recipient's own map app with one tap -- the delivery point of an order."""
        ...


class NotImplementedTelegramGateway:
    def send_message(self, telegram_username: str, title: str, body: str) -> str:
        raise NotImplementedError("No Telegram Bot API integration is registered yet. TelegramGateway is a placeholder interface, per this phase's explicit scope -- no bot token, HTTP client, or credentials configuration exists anywhere in this repository yet.")

    def send_message_with_keyboard(self, chat_id: str, text: str, inline_keyboard: list) -> str:
        raise NotImplementedError("No Telegram Bot API integration is registered yet.")

    def send_contact_request(self, chat_id: str, text: str, button_text: str) -> str:
        raise NotImplementedError("No Telegram Bot API integration is registered yet.")

    def send_location_request(self, chat_id: str, text: str, button_text: str) -> str:
        raise NotImplementedError("No Telegram Bot API integration is registered yet.")

    def edit_message_text(self, chat_id: str, message_id: str, text: str, inline_keyboard: list | None = None) -> None:
        raise NotImplementedError("No Telegram Bot API integration is registered yet.")

    def edit_message_caption(self, chat_id: str, message_id: str, caption: str, inline_keyboard: list | None = None) -> None:
        raise NotImplementedError("No Telegram Bot API integration is registered yet.")

    def send_photo(self, chat_id: str, photo_url: str, caption: str, inline_keyboard: list[list[dict]] | None = None) -> str:
        raise NotImplementedError("No Telegram Bot API integration is registered yet.")

    def edit_message_media(self, chat_id: str, message_id: str, photo_url: str, caption: str, inline_keyboard: list[list[dict]] | None = None) -> None:
        raise NotImplementedError("No Telegram Bot API integration is registered yet.")

    def send_venue(self, chat_id: str, latitude: float, longitude: float, title: str, address: str, reply_to: str | None = None, inline_keyboard: list[list[dict]] | None = None) -> str:
        raise NotImplementedError("No Telegram Bot API integration is registered yet.")


class TelegramGatewayConfigurationError(Exception):
    """Raised when the live gateway is selected but TELEGRAM_BOT_TOKEN is absent -- fails loudly at first use, never silently falls back."""


class TelegramGatewayNonRetryableError(Exception):
    """The Bot API rejected the request in a way retrying will not fix (invalid chat/username, invalid/revoked bot token, malformed response). Distinct from a transient failure (timeout, connection error, 5xx), which raises `TelegramGatewayRetryableError` instead."""


class TelegramGatewayRetryableError(Exception):
    """A transient failure (timeout, connection error, 5xx) -- safe for the caller's own existing retry infrastructure to retry."""


class LiveTelegramGateway:
    """
    Real adapter for the Telegram Bot API's own `sendMessage` endpoint
    (`https://api.telegram.org/bot<token>/sendMessage`). Unlike
    `EskizOTPProvider` (Uzbek vendor, exact field names not verifiable
    without a live sandbox account), Telegram's Bot API is stable,
    globally standardized, and its request/response shape used here
    matches its own long-published public documentation with high
    confidence.

    `telegram_username` is expected to already be a numeric chat_id or
    an `@username` the bot has an existing conversation with -- the
    Bot API cannot message an arbitrary `@username` it has no prior
    chat history with (a real, disclosed platform limitation, not a
    defect of this adapter).
    """

    def __init__(self, bot_token: str | None = None, base_url: str | None = None, timeout_seconds: float | None = None) -> None:
        from django.conf import settings

        self._bot_token = bot_token if bot_token is not None else getattr(settings, "TELEGRAM_BOT_TOKEN", None)
        self._base_url = (base_url if base_url is not None else getattr(settings, "TELEGRAM_API_BASE_URL", "https://api.telegram.org")).rstrip("/")
        self._timeout_seconds = timeout_seconds if timeout_seconds is not None else getattr(settings, "TELEGRAM_TIMEOUT_SECONDS", 10.0)

    def send_message(self, telegram_username: str, title: str, body: str) -> str:
        if not self._bot_token:
            raise TelegramGatewayConfigurationError(
                "LiveTelegramGateway selected via NUTRIZONE_TELEGRAM_GATEWAY but TELEGRAM_BOT_TOKEN is not configured. "
                "Set the environment variable, or select 'disabled'."
            )

        text = f"*{title}*\n{body}" if title else body
        try:
            # The bot token appears only in the URL path of this one request, never logged -- see this method's own exception handlers below, none of which include the URL.
            response = requests.post(
                f"{self._base_url}/bot{self._bot_token}/sendMessage",
                json={"chat_id": telegram_username, "text": text, "parse_mode": "Markdown"},
                timeout=self._timeout_seconds,
            )
        except requests.exceptions.Timeout as exc:
            logger.warning("Telegram send failed: request timed out (provider=telegram, chat=%s)", telegram_username)
            raise TelegramGatewayRetryableError("Telegram sendMessage request timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            logger.warning("Telegram send failed: connection error (provider=telegram, chat=%s)", telegram_username)
            raise TelegramGatewayRetryableError("Telegram sendMessage connection error.") from exc

        if response.status_code >= 500:
            logger.warning("Telegram send failed: server error (provider=telegram, chat=%s, status=%s)", telegram_username, response.status_code)
            raise TelegramGatewayRetryableError(f"Telegram returned a server error (HTTP {response.status_code}).")
        if response.status_code == 401 or response.status_code == 403:
            logger.error("Telegram send rejected: authorization failed (provider=telegram, chat=%s, status=%s)", telegram_username, response.status_code)
            raise TelegramGatewayNonRetryableError(f"Telegram rejected the bot token or chat access (HTTP {response.status_code}) -- check TELEGRAM_BOT_TOKEN and that the user has started a chat with the bot.")
        if response.status_code == 400:
            logger.error("Telegram send rejected: invalid request (provider=telegram, chat=%s, status=400)", telegram_username)
            raise TelegramGatewayNonRetryableError("Telegram rejected the request (HTTP 400) -- the chat_id/username is likely invalid or the bot has no existing conversation with this user.")
        if response.status_code != 200:
            logger.error("Telegram send failed: unexpected status (provider=telegram, chat=%s, status=%s)", telegram_username, response.status_code)
            raise TelegramGatewayNonRetryableError(f"Telegram returned an unexpected status code {response.status_code}.")

        try:
            body_json = response.json()
        except ValueError as exc:
            logger.error("Telegram send failed: malformed (non-JSON) response body (provider=telegram, chat=%s)", telegram_username)
            raise TelegramGatewayNonRetryableError("Telegram returned a malformed (non-JSON) response body.") from exc

        if not body_json.get("ok"):
            logger.error("Telegram send rejected: response body reports ok=false (provider=telegram, chat=%s, description=%s)", telegram_username, body_json.get("description", "<none>"))
            raise TelegramGatewayNonRetryableError(f"Telegram reported failure in the response body: {body_json.get('description', '<none>')}")

        message_id = body_json.get("result", {}).get("message_id")
        if message_id is None:
            raise TelegramGatewayNonRetryableError("Telegram reported ok=true but no message_id was present in the response body.")
        return str(message_id)

    def send_message_with_keyboard(self, chat_id: str, text: str, inline_keyboard: list[list[dict]]) -> str:
        """Phase 15C: the one genuinely needed extension beyond plain sendMessage -- catalog/cart navigation requires inline buttons. Reuses the exact same request/error-handling shape as send_message rather than a second, divergent implementation."""
        if not self._bot_token:
            raise TelegramGatewayConfigurationError(
                "LiveTelegramGateway selected via NUTRIZONE_TELEGRAM_GATEWAY but TELEGRAM_BOT_TOKEN is not configured. "
                "Set the environment variable, or select 'disabled'."
            )
        try:
            response = requests.post(
                f"{self._base_url}/bot{self._bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "reply_markup": {"inline_keyboard": inline_keyboard}},
                timeout=self._timeout_seconds,
            )
        except requests.exceptions.Timeout as exc:
            raise TelegramGatewayRetryableError("Telegram sendMessage request timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise TelegramGatewayRetryableError("Telegram sendMessage connection error.") from exc

        if response.status_code >= 500:
            raise TelegramGatewayRetryableError(f"Telegram returned a server error (HTTP {response.status_code}).")
        if response.status_code != 200:
            logger.warning("Telegram send_message_with_keyboard failed: status=%s body=%s", response.status_code, response.text[:200])
            raise TelegramGatewayNonRetryableError(f"Telegram rejected the request (HTTP {response.status_code}).")

        try:
            body_json = response.json()
        except ValueError as exc:
            raise TelegramGatewayNonRetryableError("Telegram returned a malformed (non-JSON) response body.") from exc
        if not body_json.get("ok"):
            raise TelegramGatewayNonRetryableError(f"Telegram reported failure: {body_json.get('description', '<none>')}")
        return str(body_json.get("result", {}).get("message_id", ""))

    def send_contact_request(self, chat_id: str, text: str, button_text: str) -> str:
        """Same request/error-handling shape as send_message_with_keyboard -- a reply keyboard (not inline) with a single `request_contact` button, so Telegram's own client prompts the user to share their real phone number in one tap."""
        if not self._bot_token:
            raise TelegramGatewayConfigurationError(
                "LiveTelegramGateway selected via NUTRIZONE_TELEGRAM_GATEWAY but TELEGRAM_BOT_TOKEN is not configured. "
                "Set the environment variable, or select 'disabled'."
            )
        reply_markup = {"keyboard": [[{"text": button_text, "request_contact": True}]], "resize_keyboard": True, "one_time_keyboard": True}
        try:
            response = requests.post(
                f"{self._base_url}/bot{self._bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "reply_markup": reply_markup},
                timeout=self._timeout_seconds,
            )
        except requests.exceptions.Timeout as exc:
            raise TelegramGatewayRetryableError("Telegram sendMessage request timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise TelegramGatewayRetryableError("Telegram sendMessage connection error.") from exc

        if response.status_code >= 500:
            raise TelegramGatewayRetryableError(f"Telegram returned a server error (HTTP {response.status_code}).")
        if response.status_code != 200:
            logger.warning("Telegram send_contact_request failed: status=%s body=%s", response.status_code, response.text[:200])
            raise TelegramGatewayNonRetryableError(f"Telegram rejected the request (HTTP {response.status_code}).")

        try:
            body_json = response.json()
        except ValueError as exc:
            raise TelegramGatewayNonRetryableError("Telegram returned a malformed (non-JSON) response body.") from exc
        if not body_json.get("ok"):
            raise TelegramGatewayNonRetryableError(f"Telegram reported failure: {body_json.get('description', '<none>')}")
        return str(body_json.get("result", {}).get("message_id", ""))

    def send_location_request(self, chat_id: str, text: str, button_text: str) -> str:
        """Same request/error-handling shape as send_contact_request -- a reply keyboard (not inline) with a single `request_location` button, so Telegram's own client prompts the user to share their real, device-GPS delivery location in one tap."""
        if not self._bot_token:
            raise TelegramGatewayConfigurationError(
                "LiveTelegramGateway selected via NUTRIZONE_TELEGRAM_GATEWAY but TELEGRAM_BOT_TOKEN is not configured. "
                "Set the environment variable, or select 'disabled'."
            )
        reply_markup = {"keyboard": [[{"text": button_text, "request_location": True}]], "resize_keyboard": True, "one_time_keyboard": True}
        try:
            response = requests.post(
                f"{self._base_url}/bot{self._bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "reply_markup": reply_markup},
                timeout=self._timeout_seconds,
            )
        except requests.exceptions.Timeout as exc:
            raise TelegramGatewayRetryableError("Telegram sendMessage request timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise TelegramGatewayRetryableError("Telegram sendMessage connection error.") from exc

        if response.status_code >= 500:
            raise TelegramGatewayRetryableError(f"Telegram returned a server error (HTTP {response.status_code}).")
        if response.status_code != 200:
            logger.warning("Telegram send_location_request failed: status=%s body=%s", response.status_code, response.text[:200])
            raise TelegramGatewayNonRetryableError(f"Telegram rejected the request (HTTP {response.status_code}).")

        try:
            body_json = response.json()
        except ValueError as exc:
            raise TelegramGatewayNonRetryableError("Telegram returned a malformed (non-JSON) response body.") from exc
        if not body_json.get("ok"):
            raise TelegramGatewayNonRetryableError(f"Telegram reported failure: {body_json.get('description', '<none>')}")
        return str(body_json.get("result", {}).get("message_id", ""))

    def send_venue(self, chat_id: str, latitude: float, longitude: float, title: str, address: str, reply_to: str | None = None, inline_keyboard: list[list[dict]] | None = None) -> str:
        """Bot API sendVenue -- an exact map pin with a title and address line (opens in the courier's own map app)."""
        if not self._bot_token:
            raise TelegramGatewayConfigurationError("LiveTelegramGateway selected via NUTRIZONE_TELEGRAM_GATEWAY but TELEGRAM_BOT_TOKEN is not configured.")
        payload = {"chat_id": chat_id, "latitude": latitude, "longitude": longitude, "title": title[:100], "address": address[:200]}
        if reply_to:
            payload["reply_parameters"] = {"message_id": int(reply_to), "allow_sending_without_reply": True}
        if inline_keyboard:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        try:
            response = requests.post(f"{self._base_url}/bot{self._bot_token}/sendVenue", json=payload, timeout=self._timeout_seconds)
        except requests.exceptions.Timeout as exc:
            raise TelegramGatewayRetryableError("Telegram sendVenue request timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise TelegramGatewayRetryableError("Telegram sendVenue connection error.") from exc
        if response.status_code >= 500:
            raise TelegramGatewayRetryableError(f"Telegram returned a server error (HTTP {response.status_code}).")
        if response.status_code != 200:
            logger.warning("Telegram send_venue failed: status=%s body=%s", response.status_code, response.text[:200])
            raise TelegramGatewayNonRetryableError(f"Telegram rejected the request (HTTP {response.status_code}).")
        try:
            body_json = response.json()
        except ValueError as exc:
            raise TelegramGatewayNonRetryableError("Telegram returned a malformed (non-JSON) response body.") from exc
        if not body_json.get("ok"):
            raise TelegramGatewayNonRetryableError(f"Telegram reported failure: {body_json.get('description', '<none>')}")
        return str(body_json.get("result", {}).get("message_id", ""))

    def edit_message_text(self, chat_id: str, message_id: str, text: str, inline_keyboard: list | None = None) -> None:
        """Phase 15E: edits an already-sent message -- used to remove inline buttons and show the resolved state after a manager confirms/cancels an order, preventing a second click on a stale button."""
        if not self._bot_token:
            raise TelegramGatewayConfigurationError("LiveTelegramGateway selected via NUTRIZONE_TELEGRAM_GATEWAY but TELEGRAM_BOT_TOKEN is not configured.")
        payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
        if inline_keyboard is not None:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        try:
            response = requests.post(f"{self._base_url}/bot{self._bot_token}/editMessageText", json=payload, timeout=self._timeout_seconds)
        except requests.exceptions.Timeout as exc:
            raise TelegramGatewayRetryableError("Telegram editMessageText request timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise TelegramGatewayRetryableError("Telegram editMessageText connection error.") from exc
        if response.status_code >= 500:
            raise TelegramGatewayRetryableError(f"Telegram returned a server error (HTTP {response.status_code}).")
        if response.status_code != 200:
            logger.warning("Telegram edit_message_text failed: status=%s body=%s", response.status_code, response.text[:200])
            raise TelegramGatewayNonRetryableError(f"Telegram rejected the request (HTTP {response.status_code}).")

    def edit_message_caption(self, chat_id: str, message_id: str, caption: str, inline_keyboard: list | None = None) -> None:
        """The editMessageText twin for a photo post (a photo message has a caption, not text -- editMessageText fails on it)."""
        if not self._bot_token:
            raise TelegramGatewayConfigurationError("LiveTelegramGateway selected via NUTRIZONE_TELEGRAM_GATEWAY but TELEGRAM_BOT_TOKEN is not configured.")
        payload = {"chat_id": chat_id, "message_id": message_id, "caption": caption, "parse_mode": "HTML"}
        if inline_keyboard is not None:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        try:
            response = requests.post(f"{self._base_url}/bot{self._bot_token}/editMessageCaption", json=payload, timeout=self._timeout_seconds)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            raise TelegramGatewayRetryableError("Telegram editMessageCaption request failed.") from exc
        if response.status_code >= 500:
            raise TelegramGatewayRetryableError(f"Telegram returned a server error (HTTP {response.status_code}).")
        if response.status_code != 200:
            logger.warning("Telegram edit_message_caption failed: status=%s body=%s", response.status_code, response.text[:200])
            raise TelegramGatewayNonRetryableError(f"Telegram rejected the request (HTTP {response.status_code}).")

    def send_photo(self, chat_id: str, photo_url: str, caption: str, inline_keyboard: list[list[dict]] | None = None) -> str:
        """Real Bot API sendPhoto call -- photo_url must be a real, publicly-reachable URL (Telegram's own servers fetch it directly); same request/error-handling shape as send_message_with_keyboard."""
        if not self._bot_token:
            raise TelegramGatewayConfigurationError(
                "LiveTelegramGateway selected via NUTRIZONE_TELEGRAM_GATEWAY but TELEGRAM_BOT_TOKEN is not configured. "
                "Set the environment variable, or select 'disabled'."
            )
        payload = {"chat_id": chat_id, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
        if inline_keyboard is not None:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        try:
            response = requests.post(f"{self._base_url}/bot{self._bot_token}/sendPhoto", json=payload, timeout=self._timeout_seconds)
        except requests.exceptions.Timeout as exc:
            raise TelegramGatewayRetryableError("Telegram sendPhoto request timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise TelegramGatewayRetryableError("Telegram sendPhoto connection error.") from exc

        if response.status_code >= 500:
            raise TelegramGatewayRetryableError(f"Telegram returned a server error (HTTP {response.status_code}).")
        if response.status_code != 200:
            logger.warning("Telegram send_photo failed: status=%s body=%s", response.status_code, response.text[:200])
            raise TelegramGatewayNonRetryableError(f"Telegram rejected the request (HTTP {response.status_code}).")

        try:
            body_json = response.json()
        except ValueError as exc:
            raise TelegramGatewayNonRetryableError("Telegram returned a malformed (non-JSON) response body.") from exc
        if not body_json.get("ok"):
            raise TelegramGatewayNonRetryableError(f"Telegram reported failure: {body_json.get('description', '<none>')}")
        return str(body_json.get("result", {}).get("message_id", ""))

    def edit_message_media(self, chat_id: str, message_id: str, photo_url: str, caption: str, inline_keyboard: list[list[dict]] | None = None) -> None:
        """Real Bot API `editMessageMedia` call -- same request/error-handling shape as `send_photo`/`edit_message_text`. `media` must be a JSON object per Telegram's own documented shape (`type`, `media`, `caption`), passed as a single field alongside `chat_id`/`message_id`, never as separate top-level fields (a common integration mistake with this specific endpoint)."""
        if not self._bot_token:
            raise TelegramGatewayConfigurationError(
                "LiveTelegramGateway selected via NUTRIZONE_TELEGRAM_GATEWAY but TELEGRAM_BOT_TOKEN is not configured. "
                "Set the environment variable, or select 'disabled'."
            )
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "media": {"type": "photo", "media": photo_url, "caption": caption, "parse_mode": "HTML"},
        }
        if inline_keyboard is not None:
            payload["reply_markup"] = {"inline_keyboard": inline_keyboard}
        try:
            response = requests.post(f"{self._base_url}/bot{self._bot_token}/editMessageMedia", json=payload, timeout=self._timeout_seconds)
        except requests.exceptions.Timeout as exc:
            raise TelegramGatewayRetryableError("Telegram editMessageMedia request timed out.") from exc
        except requests.exceptions.ConnectionError as exc:
            raise TelegramGatewayRetryableError("Telegram editMessageMedia connection error.") from exc

        if response.status_code >= 500:
            raise TelegramGatewayRetryableError(f"Telegram returned a server error (HTTP {response.status_code}).")
        if response.status_code != 200:
            logger.warning("Telegram edit_message_media failed: status=%s body=%s", response.status_code, response.text[:200])
            raise TelegramGatewayNonRetryableError(f"Telegram rejected the request (HTTP {response.status_code}).")

        try:
            body_json = response.json()
        except ValueError as exc:
            raise TelegramGatewayNonRetryableError("Telegram returned a malformed (non-JSON) response body.") from exc
        if not body_json.get("ok"):
            raise TelegramGatewayNonRetryableError(f"Telegram reported failure: {body_json.get('description', '<none>')}")


def get_telegram_gateway():
    """Resolves the active Telegram gateway from Django settings -- a config-driven swap point, matching NUTRIZONE_OTP_PROVIDER's own established convention. 'disabled' (the default) preserves the existing fail-loud NotImplementedTelegramGateway behavior unchanged."""
    from django.conf import settings

    gateway_name = getattr(settings, "NUTRIZONE_TELEGRAM_GATEWAY", "disabled")
    if gateway_name == "live":
        return LiveTelegramGateway()
    if gateway_name == "disabled":
        return NotImplementedTelegramGateway()
    raise ValueError(f"Unknown Telegram gateway '{gateway_name}'.")


def get_orders_telegram_gateway():
    """
    Same swap point as `get_telegram_gateway`, bound to the separate
    Orders Bot's own token (`TELEGRAM_ORDERS_BOT_TOKEN`) instead of the
    customer-facing bot's `TELEGRAM_BOT_TOKEN` -- a genuinely different
    bot (own @username), per explicit product decision, not a second
    destination chat for the same bot. Used by orders_channel_subscriber.py
    to post new orders and by callback_router._handle_manager_action to
    edit that same message after a manager confirms/cancels it, since
    only the bot that sent a message can edit it.
    """
    from django.conf import settings

    gateway_name = getattr(settings, "NUTRIZONE_TELEGRAM_GATEWAY", "disabled")
    if gateway_name == "live":
        return LiveTelegramGateway(bot_token=getattr(settings, "TELEGRAM_ORDERS_BOT_TOKEN", None))
    if gateway_name == "disabled":
        return NotImplementedTelegramGateway()
    raise ValueError(f"Unknown Telegram gateway '{gateway_name}'.")
