"""
Django System Check Framework hooks for Telegram authentication.

Real, root-cause fix for a genuine failure mode confirmed live this
phase: since SMS login is disabled by default
(NUTRIZONE_SMS_LOGIN_ENABLED=false), Telegram is the storefront's
*only* customer login path -- yet a missing TELEGRAM_BOT_USERNAME or
TELEGRAM_BOT_TOKEN previously failed *silently* at request time
(CreateTelegramAuthSessionView still returns HTTP 201 with
telegram_url=null; the "Continue with Telegram" button then does
nothing with no visible clue why). These checks surface that
misconfiguration loudly, at `manage.py check`/deploy time, instead of
leaving it to be discovered only when a real customer clicks a real
button in production.
"""
from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Warning, register

# Real, live-observed failure mode this check exists to catch: a
# developer runs the backend locally behind a temporary HTTP tunnel
# (cloudflared/ngrok/localtunnel) to receive real Telegram webhook
# callbacks against their own machine, and sets FRONTEND_URL to that
# same throwaway tunnel domain to test the "Saytga avtomatik kirish"
# button end-to-end. That value is then left behind (in a shared
# .env, a copied deploy config, ...) and the bot goes on handing real
# customers a login link pointing at a URL that stops resolving the
# moment the developer's tunnel process exits -- with zero error or
# warning anywhere. These host suffixes are the tunnel providers most
# commonly used for exactly this kind of local testing.
_KNOWN_TEMPORARY_TUNNEL_HOST_SUFFIXES = (
    "trycloudflare.com",
    "ngrok.io",
    "ngrok-free.app",
    "ngrok.app",
    "loca.lt",
    "serveo.net",
    "localhost.run",
)


def _looks_like_a_temporary_tunnel_domain(url: str) -> bool:
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in _KNOWN_TEMPORARY_TUNNEL_HOST_SUFFIXES)


@register()
def check_telegram_auth_is_configured(app_configs, **kwargs):
    """
    If Telegram is the sole customer login path (the current,
    intentional default), both TELEGRAM_BOT_TOKEN and
    TELEGRAM_BOT_USERNAME are load-bearing for every customer-facing
    auth flow -- their absence is a deploy-blocking configuration
    error, not a soft warning, since no customer could otherwise log
    in or register at all.
    """
    errors = []
    sms_enabled = getattr(settings, "NUTRIZONE_SMS_LOGIN_ENABLED", False)
    bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
    bot_username = getattr(settings, "TELEGRAM_BOT_USERNAME", None)

    if not sms_enabled and not bot_token:
        errors.append(Error(
            "TELEGRAM_BOT_TOKEN is not configured, and NUTRIZONE_SMS_LOGIN_ENABLED is false -- "
            "Telegram is the only customer login path, but no customer could authenticate at all.",
            hint="Set the TELEGRAM_BOT_TOKEN environment variable, or set NUTRIZONE_SMS_LOGIN_ENABLED=true as a temporary fallback.",
            id="telegram_bot.E001",
        ))
    if not sms_enabled and not bot_username:
        errors.append(Error(
            "TELEGRAM_BOT_USERNAME is not configured, and NUTRIZONE_SMS_LOGIN_ENABLED is false -- "
            "the website's own \"Continue with Telegram\" button will create a session successfully "
            "(HTTP 201) but its telegram_url will be null, so the button silently does nothing.",
            hint="Set the TELEGRAM_BOT_USERNAME environment variable to your bot's real @username (without the @).",
            id="telegram_bot.E002",
        ))

    if not getattr(settings, "TELEGRAM_WEBHOOK_SECRET", None):
        errors.append(Warning(
            "TELEGRAM_WEBHOOK_SECRET is not configured -- the real Telegram webhook endpoint "
            "(/api/v1/telegram/webhook) will reject every incoming update from Telegram, since it "
            "requires this secret to verify the request actually came from Telegram's servers.",
            hint="Set the TELEGRAM_WEBHOOK_SECRET environment variable to a real, random secret, and pass the same value when calling `telegram_set_webhook`.",
            id="telegram_bot.W001",
        ))

    # Unlike bot_token/bot_username above, this is never gated on
    # sms_enabled: the bot's "Saytga avtomatik kirish" menu button is
    # shown to every linked customer unconditionally (see
    # callback_router._main_menu_keyboard), regardless of whether SMS
    # login also exists as a fallback -- so a missing FRONTEND_URL
    # breaks that button either way.
    frontend_url = getattr(settings, "FRONTEND_URL", None)
    if not frontend_url:
        errors.append(Warning(
            "FRONTEND_URL is not configured -- the bot's \"Saytga avtomatik kirish\" (auto-login) "
            "menu button cannot build a login link and will show the customer a technical-error "
            "message every time it is pressed.",
            hint="Set the FRONTEND_URL environment variable to the storefront's real public origin, e.g. https://nutrizone.uz (no trailing slash).",
            id="telegram_bot.W002",
        ))
    elif frontend_url and _looks_like_a_temporary_tunnel_domain(frontend_url):
        # A real, live-confirmed misconfiguration, not a hypothetical one: a
        # customer-facing Telegram auto-login link was observed pointing at a
        # throwaway *.trycloudflare.com tunnel -- this is always a mistake in
        # any environment where real customers can reach the bot, since that
        # tunnel is guaranteed to stop resolving the moment whoever started it
        # closes their terminal.
        errors.append(Warning(
            f"FRONTEND_URL is set to {frontend_url!r}, which looks like a temporary development "
            "tunnel domain, not a real production frontend origin. Every customer who presses "
            "\"Saytga avtomatik kirish\" will receive a login link that stops working the moment "
            "this tunnel is closed.",
            hint=(
                "Set FRONTEND_URL to the storefront's real, stable public domain (e.g. https://nutrizone.uz) "
                "before customers can reach this bot. If you're still using the Quick Tunnel Docker Compose "
                "profile (docker-compose.yml's own comment on cloudflared-quick explains why its domain "
                "changes every restart), switch to the cloudflared-named profile or your real domain first."
            ),
            id="telegram_bot.W003",
        ))

    # Only checked when the Orders Channel feature is actually meant to be
    # active (TELEGRAM_ORDERS_CHAT_ID set) -- matches
    # sync_orders_channel()'s own "blank chat id means inactive" gate, so
    # an environment that never opted into this feature is never warned
    # about it.
    orders_chat_id = getattr(settings, "TELEGRAM_ORDERS_CHAT_ID", "")
    if orders_chat_id:
        if not getattr(settings, "TELEGRAM_ORDERS_BOT_TOKEN", None):
            errors.append(Warning(
                "TELEGRAM_ORDERS_CHAT_ID is configured but TELEGRAM_ORDERS_BOT_TOKEN is not -- "
                "the separate Orders Bot (see orders_channel_subscriber.py) cannot post new orders "
                "to the Orders Channel at all.",
                hint="Create a bot via @BotFather and set TELEGRAM_ORDERS_BOT_TOKEN to its token.",
                id="telegram_bot.W004",
            ))
        if not getattr(settings, "TELEGRAM_ORDERS_WEBHOOK_SECRET", None):
            errors.append(Warning(
                "TELEGRAM_ORDERS_CHAT_ID is configured but TELEGRAM_ORDERS_WEBHOOK_SECRET is not -- "
                "the Orders Bot's webhook (/api/v1/telegram/orders-webhook) will reject every "
                "incoming update, so the Confirm/Cancel buttons will not work.",
                hint="Set the TELEGRAM_ORDERS_WEBHOOK_SECRET environment variable to a real, random secret, and pass the same value when calling `telegram_set_webhook --bot orders`.",
                id="telegram_bot.W005",
            ))

    return errors
