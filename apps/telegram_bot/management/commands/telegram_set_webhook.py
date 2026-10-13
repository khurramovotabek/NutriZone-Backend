"""
`python manage.py telegram_set_webhook` -- registers this deployment's
public webhook URL with the real Telegram Bot API's own `setWebhook`
endpoint, so Telegram starts delivering updates here.

This is the real, missing piece behind "the bot should start when the
backend starts": Telegram's Bot API is webhook-based, not a polling
process (confirmed by direct inspection -- no runbot/polling loop
exists anywhere in this codebase, and none is needed). There is
nothing to "start" as a long-running process; the bot IS the
`/api/v1/telegram/webhook` Django view, already live the moment the
web server itself is. The one missing step was telling Telegram where
to send updates -- this command does exactly that, idempotently (safe
to call on every deploy).

Deliberately a management command, not `AppConfig.ready()`: `ready()`
runs on every management command invocation (migrate, shell, test,
collectstatic), where firing a real, blocking HTTP call to Telegram
would be surprising, slow, and would spuriously fail in CI/sandbox
environments with no real bot token. A command run explicitly once
per deploy (e.g. from a Docker entrypoint or a post-deploy hook) is
the correct, standard Django pattern for this kind of one-time,
environment-dependent side effect.
"""
from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


# The update types the bot handles: messages, button presses and inline-mode queries (`@bot protein`).
ALLOWED_UPDATES = ["message", "callback_query", "inline_query"]

class Command(BaseCommand):
    help = "Registers this deployment's public webhook URL with the Telegram Bot API's setWebhook endpoint."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url", type=str, default=None,
            help="Override the full public webhook URL. Defaults to f'{settings.PUBLIC_BASE_URL}/api/v1/telegram/webhook' (or /orders-webhook for --bot orders).",
        )
        parser.add_argument("--delete", action="store_true", help="Delete the webhook instead of setting it (calls deleteWebhook).")
        parser.add_argument(
            "--bot", choices=["customer", "orders", "analytics"], default="customer",
            help="Which bot to register the webhook for: 'customer' (default, TELEGRAM_BOT_TOKEN), 'orders' (the separate Orders Bot, TELEGRAM_ORDERS_BOT_TOKEN) or 'analytics' (NutriZoneAnalyticsBot, TELEGRAM_ANALYTICS_BOT_TOKEN).",
        )

    def handle(self, *args, **options):
        import requests

        target = options["bot"]
        allowed_updates = ALLOWED_UPDATES
        if target == "analytics":
            bot_token = getattr(settings, "TELEGRAM_ANALYTICS_BOT_TOKEN", None)
            webhook_secret = getattr(settings, "TELEGRAM_ANALYTICS_WEBHOOK_SECRET", None)
            default_path = "analytics-webhook"
            token_setting_name = "TELEGRAM_ANALYTICS_BOT_TOKEN"
            secret_setting_name = "TELEGRAM_ANALYTICS_WEBHOOK_SECRET"
            allowed_updates = ["message", "callback_query"]
        elif target == "orders":
            bot_token = getattr(settings, "TELEGRAM_ORDERS_BOT_TOKEN", None)
            webhook_secret = getattr(settings, "TELEGRAM_ORDERS_WEBHOOK_SECRET", None)
            default_path = "orders-webhook"
            token_setting_name = "TELEGRAM_ORDERS_BOT_TOKEN"
            secret_setting_name = "TELEGRAM_ORDERS_WEBHOOK_SECRET"
        else:
            bot_token = getattr(settings, "TELEGRAM_BOT_TOKEN", None)
            webhook_secret = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", None)
            default_path = "webhook"
            token_setting_name = "TELEGRAM_BOT_TOKEN"
            secret_setting_name = "TELEGRAM_WEBHOOK_SECRET"
        base_api_url = getattr(settings, "TELEGRAM_API_BASE_URL", "https://api.telegram.org").rstrip("/")

        if not bot_token:
            raise CommandError(f"{token_setting_name} is not configured -- cannot call the Telegram Bot API.")

        if options["delete"]:
            response = requests.post(f"{base_api_url}/bot{bot_token}/deleteWebhook", timeout=10.0)
            self._report(response, "Webhook deleted.")
            return

        webhook_url = options["url"] or self._default_webhook_url(default_path)
        if not webhook_url:
            raise CommandError("No webhook URL given and PUBLIC_BASE_URL is not configured -- pass --url explicitly.")
        if not webhook_secret:
            raise CommandError(f"{secret_setting_name} is not configured -- refusing to register a webhook with no secret token (see telegram_webhook_view's own security requirement).")

        # Real, closed production bug: this command previously called
        # setWebhook unconditionally on every invocation. AppConfig.
        # ready()'s own auto-registration thread runs this once per
        # "web" process start -- with several gunicorn workers, or a
        # `runserver` dev-server reload, several of those calls land on
        # Telegram within the same couple of seconds, and Telegram's own
        # API throttles repeated setWebhook calls for one bot with
        # "Too Many Requests: retry after N" (confirmed exact production
        # log message). Checking the currently-registered webhook first
        # and skipping the call entirely when it already matches turns
        # every no-op restart (the overwhelming majority of real calls)
        # into zero Telegram API traffic at all -- never a new HTTP
        # client, just the same `requests` call this file already made.
        if self._already_registered(base_api_url, bot_token, webhook_url, allowed_updates):
            self.stdout.write(self.style.SUCCESS(f"Webhook already correctly registered: {webhook_url}"))
            return

        # Second layer, for the remaining real case (a genuinely new/
        # changed URL, e.g. first deploy or a rotated tunnel domain):
        # several workers could all observe "not yet registered" above
        # in the same instant and all race to call setWebhook together,
        # which is exactly the failure this bug report describes. A
        # short Redis lock (same `get_redis_client()` this app's own
        # onboarding_state.py already uses for short-lived state) lets
        # exactly one of them win; the rest skip silently rather than
        # erroring, since the winner's call covers all of them.
        from core.caching.redis_client import cache_key, get_redis_client

        lock_key = cache_key(webhook_url, namespace="telegram_bot:webhook_registration_lock")
        try:
            acquired = get_redis_client().set(lock_key, "1", nx=True, ex=30)
        except Exception:  # noqa: BLE001 -- Redis being unavailable must never block a real webhook registration; fail open on the lock only.
            acquired = True

        if not acquired:
            self.stdout.write(self.style.SUCCESS("Webhook registration already in progress on another process -- skipping."))
            return

        payload = {"url": webhook_url, "secret_token": webhook_secret, "allowed_updates": allowed_updates}
        response = requests.post(f"{base_api_url}/bot{bot_token}/setWebhook", json=payload, timeout=10.0)
        self._report(response, f"Webhook registered: {webhook_url}")

    def _already_registered(self, base_api_url: str, bot_token: str, webhook_url: str, allowed_updates=ALLOWED_UPDATES) -> bool:
        import requests

        try:
            response = requests.get(f"{base_api_url}/bot{bot_token}/getWebhookInfo", timeout=10.0)
            body = response.json()
        except Exception:  # noqa: BLE001 -- unknown current state must never block registration; proceed to (re)register.
            return False
        if not body.get("ok"):
            return False
        result = body.get("result", {})
        # A webhook missing an update type (e.g. "inline_query", added for inline mode) must be re-registered.
        return result.get("url") == webhook_url and set(result.get("allowed_updates") or []) == set(allowed_updates)

    def _default_webhook_url(self, path: str) -> str | None:
        base = getattr(settings, "PUBLIC_BASE_URL", None)
        if not base:
            return None
        return f"{base.rstrip('/')}/api/v1/telegram/{path}"

    def _report(self, response, success_message: str) -> None:
        try:
            body = response.json()
        except ValueError as exc:
            raise CommandError(f"Telegram API returned a non-JSON response (status {response.status_code}): {response.text[:500]}") from exc

        if not body.get("ok"):
            raise CommandError(f"Telegram API rejected the request: {body.get('description', body)}")

        self.stdout.write(self.style.SUCCESS(success_message))
